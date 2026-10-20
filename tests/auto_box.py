#!/usr/bin/env python3
"""Check automatic box changes with disposable saves and compiled game code."""

import argparse
from pathlib import Path

from save_compatibility import Game, make_official_save, make_box, encoded_name, check_continue


def cartridge_ram(game):
    memory = game.memory
    memory[0x0000] = 0x0A
    result = bytearray()
    for bank in range(4):
        memory[0x4000] = bank
        result.extend(memory[0xA000:0xC000])
    memory[0x0000] = 0
    return bytes(result)


def load(game):
    for name in ("LoadSAV0", "LoadSAV1", "LoadSAV2"):
        assert not game.call(name) & 0x10, name


def stub(game, name, callback=None):
    game.memory[game.symbols[name]] = 0xC9
    if callback:
        game.emulator.hook_register(*game.symbols[name], lambda _: callback(), None)


def quiet_interface(game):
    # Keep capture, Pokemon data, inventory, and saving code intact. Only
    # drawing, sound, and the name-entry UI return immediately.
    for name in ("PrintText", "PrintPredefTextID", "ClearSprites", "RunDefaultPaletteCommand",
                 "LoadScreenTilesFromBuffer1", "MoveAnimation", "ShowPokedexData",
                 "SaveScreenTilesToBuffer2", "LoadScreenTilesFromBuffer2",
                 "PlaySoundWaitForCurrent", "WaitForSoundToFinish", "DelayFrame"):
        stub(game, name)
    stub(game, "AskName", lambda: game.write("wBoxMon1Nick", encoded_name("CAUGHT")))


def fixture(rom, base_save, current, counts, initialized=True):
    game = Game(rom, base_save)
    try:
        load(game)
        game.call("EmptyAllSRAMBoxes")
        boxes = []
        for number, count in enumerate(counts):
            data = bytearray(make_box(game, 1))
            data[0] = count
            data[count + 1] = 0xFF
            # Give each box a different, valid nickname for loss/duplication checks.
            for slot in range(20):
                offset = game.address("wBoxMon1Nick") - game.address("wBoxDataStart") + slot * 11
                data[offset:offset + 11] = encoded_name(chr(65 + number) + chr(65 + slot))
            boxes.append(bytes(data))
            game.write("wBoxDataStart", data)
            bank, address = game.symbols[f"sBox{number + 1}"]
            game.call("CopyBoxToOrFromSRAM", HL=game.address("wBoxDataStart"),
                      D=address >> 8, E=address & 0xFF, B=bank)
        game.write("wBoxDataStart", boxes[current])
        game.write("wCurrentBoxNum", current | (0x80 if initialized else 0))
        if initialized:
            bank, address = game.symbols[f"sBox{current + 1}"]
            game.memory[0x0000] = 0x0A
            game.memory[0x4000] = bank
            game.memory[address:address + 2] = [0, 0xFF]
            game.call("AutoBoxUpdateChecksums")
        game.write("wNumBagItems", 1)
        game.write("wBagItems", [1, 5, 0xFF])  # Master Balls
        game.write("wPokedexOwned", b"\xff" * 19)
        game.call("SaveSAVtoSRAM")
        return game.stop(save=True), boxes
    finally:
        game.stop()


def check_checksums(game):
    data = cartridge_ram(game)
    for bank in (2, 3):
        start = bank * 0x2000
        size = game.address("wBoxDataEnd") - game.address("wBoxDataStart")
        end = start + size * 6
        assert data[end] == (~sum(data[start:end]) & 0xFF), "Box-bank checksum"
        for number in range(6):
            box = data[start + number * size:start + (number + 1) * size]
            assert data[end + number + 1] == (~sum(box) & 0xFF), "Individual box checksum"


def read_saved_boxes(game):
    data = cartridge_ram(game)
    size = game.address("wBoxDataEnd") - game.address("wBoxDataStart")
    active = game.read("wCurrentBoxNum")[0] & 0x7F
    boxes = []
    for number in range(12):
        if number == active:
            boxes.append(game.read("wBoxDataStart", size))
        else:
            bank, address = game.symbols[f"sBox{number + 1}"]
            start = bank * 0x2000 + address - 0xA000
            boxes.append(data[start:start + size])
    return boxes


def check_capture(original, fixed, save, boxes, old, target, safari=False):
    game = Game(fixed, save)
    try:
        load(game)
        quiet_interface(game)
        before = cartridge_ram(game)
        game.write("wIsInBattle", 1)
        game.write("wBattleType", 2 if safari else 0)
        game.write("wNumSafariBalls", 30)
        game.write("wcf91", 8 if safari else 1)
        if safari:
            stub(game, "Random", lambda: setattr(game.emulator.register_file, "A", 0))
        game.write("wWhichPokemon", 0)
        game.write("wEnemyMonSpecies2", 0x99)  # Bulbasaur
        game.write("wCurEnemyLevel", 10)
        game.call("LoadEnemyMonData")
        game.call("ItemUseBall")
        assert game.read("wCapturedMonSpecies") == b"\x99", "Capture failed"
        assert game.read("wCurrentBoxNum") == bytes([0x80 | target]), "Wrong next box"
        assert game.read("wAutoBoxChangePending") == bytes([0x81 + old])
        assert game.read("wBoxCount")[0] == boxes[target][0] + 1
        assert game.read("wBoxMon1") == b"\x99"
        assert game.read("wBoxMon1Nick", 11) == encoded_name("CAUGHT")
        assert game.read("wBagItems", 3) == bytes([1, 5 if safari else 4, 0xFF]), "Wrong ball count"
        assert game.read("wNumSafariBalls") == bytes([29 if safari else 30])
        new_box = game.region("wBoxDataStart", "wBoxDataEnd")
        for label, length in (("wBoxMon1", 33), ("wBoxMon1OT", 11), ("wBoxMon1Nick", 11)):
            start = game.address(label) - game.address("wBoxDataStart")
            count = boxes[target][0]
            assert new_box[start + length:start + (count + 1) * length] == boxes[target][start:start + count * length]
        during = cartridge_ram(game)
        # Only the unused temporary area may change before the post-battle save.
        temp = 0x2000 + game.address("sAutoBoxBuffer") - 0xA000
        assert before[:temp] == during[:temp]
        assert before[temp + len(new_box):] == during[temp + len(new_box):]
        game.call("FinishAutoBoxChange")
        assert cartridge_ram(game) == during, "Saved during battle"
        # Reset during capture must still load the complete previous game.
        previous = Game(original, during)
        try:
            load(previous)
            assert read_saved_boxes(previous) == boxes
        finally:
            previous.stop()
        game.write("wIsInBattle", 0)
        # A map-script marker must reach the save. JoypadOverworld must call
        # the script before it commits the changed box.
        marker = game.address("wEventFlags") + 30
        stub(game, "RunMapScript", lambda: game.memory.__setitem__(marker, 0xA6))
        stub(game, "Joypad")
        game.write("wStatusFlags5", 0)
        game.call("JoypadOverworld")
        assert game.read("wAutoBoxChangePending") == b"\x00"
        expected = boxes.copy()
        expected[target] = new_box
        assert read_saved_boxes(game) == expected, "A box was lost or changed"
        check_checksums(game)
        committed = cartridge_ram(game)
        assert committed[0x2000 + game.address("sMainData") - 0xA000
                         + marker - game.address("wMainDataStart")] == 0xA6
        snapshot = game.snapshot()
        for rom in (fixed, original):
            reloaded = Game(rom, committed)
            try:
                load(reloaded)
                assert read_saved_boxes(reloaded) == expected, "Box did not survive reload"
                reloaded.call("SaveSAVtoSRAM")
                assert cartridge_ram(reloaded) == committed, "Resave changed storage"
            finally:
                reloaded.stop()
        return committed, snapshot
    finally:
        game.stop()


def check_blocked_and_bypassed(fixed, save):
    game = Game(fixed, save)
    try:
        load(game)
        before = cartridge_ram(game)
        quiet_interface(game)
        # Link play fills this six-byte preamble. The pending-save flag must
        # live outside it, and returning from link play must not save a box.
        game.write("wSerialPlayerDataBlock", b"\xfd" * 6)
        assert game.read("wAutoBoxChangePending") == b"\x00"
        game.call("FinishAutoBoxChange")
        assert cartridge_ram(game) == before
        game.write("wBoxCount", 19)
        game.call("AutoChangeBox")
        assert game.read("wAutoBoxChangePending") == b"\x00"
        assert cartridge_ram(game) == before
        game.write("wBoxCount", 20)
        allowed = []
        stub(game, "ItemUseBall.canUseBall", lambda: allowed.append(True))
        game.write("wIsInBattle", 1)
        game.write("wBattleType", 0)
        game.write("wActionResultOrTookBattleTurn", 1)
        game.call("ItemUseBall")
        assert not allowed and game.read("wActionResultOrTookBattleTurn") == b"\x00"
        assert game.read("wBagItems", 3) == bytes([1, 5, 0xFF])
        assert cartridge_ram(game) == before
        # A free party slot still accepts captures even when all boxes are full.
        game.write("wPartyCount", 5)
        game.call("ItemUseBall")
        assert len(allowed) == 1
        game.write("wPartyCount", 6)
        game.write("wBattleType", 1)  # Old man's demonstration
        game.call("ItemUseBall")
        assert len(allowed) == 2
        assert cartridge_ram(game) == before
    finally:
        game.stop()


def check_failed_throw(fixed, save):
    game = Game(fixed, save)
    try:
        load(game)
        quiet_interface(game)
        before = cartridge_ram(game)
        game.write("wIsInBattle", 1)
        game.write("wBattleType", 0)
        game.write("wCurMap", 0x8E)  # Pokemon Tower without a Silph Scope
        game.write("wcf91", 1)
        game.call("ItemUseBall")
        assert game.read("wCapturedMonSpecies") == b"\x00"
        assert game.read("wAutoBoxChangePending") == b"\x00"
        assert game.read("wBoxCount") == b"\x14"
        assert game.read("wBagItems", 3) == bytes([1, 4, 0xFF])
        assert cartridge_ram(game) == before
    finally:
        game.stop()


def check_playthrough(fixed, base_save, bag=None):
    counts = [20] * 12
    counts[11] = 19
    save, _ = fixture(fixed, base_save, 10, counts)
    if bag:
        prepared = Game(fixed, save)
        try:
            load(prepared)
            prepared.write("wNumBagItems", bag)
            prepared.call("SaveSAVtoSRAM")
            save = prepared.stop(save=True)
        finally:
            prepared.stop()
    game = Game(fixed, save)
    seen, message, displays = set(), [], []
    try:
        # Run the whole game with real menus, text, graphics, sound, and timing.
        for name in ("DisplayBattleMenu", "DisplayListMenuIDLoop", "ItemUseBall", "AskName", "FinishAutoBoxChange"):
            game.emulator.hook_register(*game.symbols[name], lambda _, n=name: seen.add(n), None)

        def text_started(_):
            if game.emulator.register_file.HL == game.address("AutoBoxChangedText"):
                message.append(True)

        def text_ready(_):
            if message:
                bank, address = game.symbols["FontGraphics"]
                start = bank * 0x4000 + address % 0x4000
                font = fixed.read_bytes()[start:start + 1024]
                expected = bytes(value for value in font for _ in range(2))
                displays.append((game.read("wTileMap", 360)[281:298],
                                 bytes(game.memory[0x8800:0x9000]) == expected,
                                 game.read("hWY"), game.read("hAutoBGTransferEnabled")))

        game.emulator.hook_register(*game.symbols["PrintText_NoCreatingTextBox"], text_started, None)
        game.emulator.hook_register(*game.symbols["PromptText"], text_ready, None)

        def wait_until(predicate, button=None):
            for frame in range(3000):
                if predicate():
                    return
                if button and frame % 20 == 0:
                    game.emulator.button(button)
                game.emulator.tick(1, False)
            raise AssertionError(f"Playthrough stopped: {seen}")

        game.open_main_menu()
        game.wait_for("OverworldLoop", frames=900, button="a")
        game.write("wCurOpponent", 0x99)
        game.write("wCurEnemyLevel", 10)
        wait_until(lambda: "DisplayBattleMenu" in seen, "a")
        game.emulator.tick(20, False)
        game.emulator.button("down")
        game.emulator.tick(12, False)
        game.emulator.button("a")
        game.emulator.tick(30, False)
        if bag:
            wait_until(lambda: "DisplayListMenuIDLoop" in seen)
            for _ in range(120):
                selected = game.read("wListScrollOffset")[0] + game.read("wCurrentMenuItem")[0]
                if selected == 39:
                    break
                game.emulator.button("down")
                game.emulator.tick(12, False)
            assert selected == 39, "Could not scroll to bag slot 40"
        wait_until(lambda: "ItemUseBall" in seen, "a")
        wait_until(lambda: "AskName" in seen, "a")
        game.emulator.tick(30, False)
        game.emulator.button("b")
        game.emulator.tick(30, False)
        wait_until(lambda: bool(message), "a")
        wait_until(lambda: bool(displays))
        # Literal screen characters for "Now using BOX 12.". The font must be
        # loaded, and the text window and background transfer must be enabled.
        assert displays[0] == (bytes.fromhex("8daeb67fb4b2a8ada67f818e977ff7f8e8"), True, b"\x00", b"\x01"), displays
        assert game.read("wCurrentBoxNum") == b"\x8b"
        assert game.read("wBoxCount") == b"\x14"
        assert game.read("wAutoBoxChangePending") == b"\x00"
        assert game.read("wIsInBattle") == b"\x00"
        if bag:
            expected_bag = bytearray(bag)
            expected_bag[80] -= 1  # quantity in slot 40
            assert game.read("wNumBagItems", len(bag)) == bytes(expected_bag)
        game.emulator.button("a")
        game.emulator.tick(60, False)
        saved = cartridge_ram(game)
        reloaded = Game(fixed, saved)
        try:
            load(reloaded)
            if bag:
                assert reloaded.read("wNumBagItems", len(bag)) == bytes(expected_bag)
            expected = reloaded.snapshot()
        finally:
            reloaded.stop()
        check_continue(fixed, saved, expected)
    finally:
        game.stop()


def check_color(original, fixed, color):
    base_save, _, _ = make_official_save(original)
    scenarios = [(0, 1, 19), (5, 8, 3), (11, 0, 0)]
    continued = None
    for old, target, count in scenarios:
        counts = [20] * 12
        counts[target] = count
        save, boxes = fixture(fixed, base_save, old, counts)
        game = Game(fixed, save)
        try:
            load(game)
            before = cartridge_ram(game)
            assert not game.call("FindNextBoxWithSpace") & 0x10
            assert game.emulator.register_file.A == target
            assert cartridge_ram(game) == before
        finally:
            game.stop()
        continued = check_capture(original, fixed, save, boxes, old, target, safari=old == 5)
        check_failed_throw(fixed, save)
    full, _ = fixture(fixed, base_save, 7, [20] * 12)
    check_blocked_and_bypassed(fixed, full)
    # Before the first manual box change, SRAM box counts can be garbage.
    first, _ = fixture(fixed, base_save, 0, [20] * 12, initialized=False)
    game = Game(fixed, first)
    try:
        load(game)
        quiet_interface(game)
        game.call("AutoChangeBox")
        assert game.read("wCurrentBoxNum") == b"\x81"
        assert game.read("wBoxCount") == b"\x00"
        game.call("FinishAutoBoxChange")
        assert game.read("wAutoBoxChangePending") == b"\x00"
        assert [box[0] for box in read_saved_boxes(game)] == [20] + [0] * 11
        check_checksums(game)
    finally:
        game.stop()
    check_continue(fixed, *continued)
    check_playthrough(fixed, base_save)
    print(f"{color}: capture, skipped boxes, wraparound, reset before saving, "
          "post-script save, original-ROM reload, first change, full storage, and Continue passed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dir", type=Path, required=True)
    parser.add_argument("--fixed-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    for color in ("red", "green", "blue"):
        name = f"pokesolus{color}.gbc"
        check_color(args.original_dir / name, args.fixed_dir / name, color)
