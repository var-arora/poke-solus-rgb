#!/usr/bin/env python3
"""Check the 40-slot bag with game routines, menus, and disposable saves."""

import argparse
from pathlib import Path

from auto_box import cartridge_ram, load, fixture, quiet_interface, read_saved_boxes, check_playthrough, stub
from save_compatibility import Game, make_official_save, check_continue


# Real item IDs, excluding the unused badge items and other dummy entries.
ALL_ITEMS = ([2, 3, 4, 5, 6] + list(range(0x0A, 0x15)) + list(range(0x1D, 0x2C))
         + list(range(0x2D, 0x32)) + list(range(0x33, 0x4C)))
ITEMS = ALL_ITEMS[:39] + [1]
FULL_BAG = [(item, index % 98 + 1) for index, item in enumerate(ITEMS)]


def bag_bytes(items):
    return bytes([len(items)] + [value for pair in items for value in pair] + [0xFF])


def set_bag(game, items):
    game.write("wNumBagItems", bag_bytes(items))


def check_bag(game, items):
    expected = bag_bytes(items)
    actual = game.read("wNumBagItems", len(expected))
    assert actual == expected, f"Bag differs: expected {expected.hex()}, got {actual.hex()}"


def add(game, item, quantity=1, pc=False):
    game.write("wcf91", item)
    game.write("wItemQuantity", quantity)
    result = game.call("AddItemToInventory", HL=game.address("wNumBoxItems" if pc else "wNumBagItems"))
    assert game.read("wItemQuantity") == bytes([quantity])
    return bool(result & 0x10)


def remove(game, index, quantity=1):
    game.write("wWhichPokemon", index)
    game.write("wItemQuantity", quantity)
    game.call("RemoveItemFromInventory", HL=game.address("wNumBagItems"))


def check_old_saves(source, fixed):
    save, _, _ = make_official_save(source)
    # Import both an empty bag and a completely full original bag. Dirty bytes
    # in the old unused space must not be mistaken for an expanded bag.
    for items, fill in (([], 0xFF), (FULL_BAG[:20], 0xA5)):
        original = Game(source, save)
        try:
            load(original)
            set_bag(original, items)
            original.memory[0xD66A:0xD6F0] = bytes([fill]) * 134
            original.call("SaveSAVtoSRAM")
            legacy_save = original.stop(save=True)
        finally:
            original.stop()
        game = Game(fixed, legacy_save)
        try:
            load(game)
            check_bag(game, items)
            assert game.read("wBagSaveVersion", 4) == b"BAG\x01"
            assert cartridge_ram(game) == legacy_save, "Loading wrote to the save"
            assert add(game, 0xC9), "Could not add an item after importing an old bag"
            check_bag(game, items + [(0xC9, 1)])
            game.call("SaveSAVtoSRAM")
            updated = game.stop(save=True)
        finally:
            game.stop()
        game = Game(fixed, updated)
        try:
            load(game)
            check_bag(game, items + [(0xC9, 1)])
        finally:
            game.stop()


def check_inventory(fixed, save):
    game = Game(fixed, save)
    try:
        load(game)
        before = game.snapshot()
        set_bag(game, [])
        expected = []
        # Add each slot through the actual inventory routine, including 21 and 40.
        for item, quantity in FULL_BAG:
            assert add(game, item, quantity)
            expected.append((item, quantity))
            check_bag(game, expected)
        assert not add(game, 0xC9), "Bag accepted a 41st slot"
        check_bag(game, expected)
        item, quantity = expected[-1]
        assert add(game, item, 99 - quantity), "A full bag rejected an existing stack"
        expected[-1] = (item, 99)
        check_bag(game, expected)
        assert not add(game, item), "Full stack overflowed a full bag"
        check_bag(game, expected)
        # Remove the final slot, then a middle slot. Check the complete order.
        remove(game, 39, 99)
        expected.pop()
        check_bag(game, expected)
        remove(game, 20, expected[20][1])
        expected.pop(20)
        check_bag(game, expected)
        # Split a stack at 99 into another slot beyond the old 20-slot limit.
        item, quantity = expected[30]
        assert add(game, item, 100 - quantity)
        expected[30] = (item, 99)
        expected.append((item, 1))
        check_bag(game, expected)
        # Script gifts use GiveItem, the same entry point as item pickups.
        assert game.call("GiveItem", B=0xC9, C=3) & 0x10
        expected.append((0xC9, 3))
        check_bag(game, expected)
        assert not game.call("IsItemInBag", B=0xC9) & 0x80
        assert game.emulator.register_file.B == 3
        # The PC still holds 50 item slots, using its original storage.
        game.write("wNumBoxItems", bag_bytes([]))
        for item in ALL_ITEMS[:50]:
            assert add(game, item, pc=True)
        assert not add(game, 0xC9, pc=True)
        assert game.read("wNumBoxItems", 102) == bag_bytes([(item, 1) for item in ALL_ITEMS[:50]])
        # Inventory changes must not overwrite money, flags, or Pokemon data.
        after = game.snapshot()
        main = bytearray(after["main"])
        for start_name, end in (("wNumBagItems", game.address("wExpandedBagEnd")),
                                ("wNumBoxItems", game.address("wBoxItems") + 101)):
            start = game.address(start_name) - game.address("wMainDataStart")
            end -= game.address("wMainDataStart")
            main[start:end] = before["main"][start:end]
        after["main"] = bytes(main)
        assert after == before, "An inventory operation changed unrelated saved fields"
    finally:
        game.stop()


def check_full_save(fixed, save):
    game = Game(fixed, save)
    try:
        load(game)
        set_bag(game, FULL_BAG)
        # The final slots hold ordinary items and retain their quantities.
        game.call("SaveSAVtoSRAM")
        expected = game.snapshot()
        updated = game.stop(save=True)
        assert len(updated) == 32768
        assert game.read("wLegacyNumBagItems") == b"\x14"
        assert game.read("wLegacyBagItems", 41) == bag_bytes(FULL_BAG[:20])[1:]
    finally:
        game.stop()
    reloaded = Game(fixed, updated)
    try:
        load(reloaded)
        check_bag(reloaded, FULL_BAG)
        assert reloaded.snapshot() == expected
        reloaded.call("SaveSAVtoSRAM")
        assert cartridge_ram(reloaded) == updated, "Repeated saving changed data"
    finally:
        reloaded.stop()
    check_continue(fixed, updated, expected)
    return updated


def check_swapping(fixed, save):
    game = Game(fixed, save)
    try:
        load(game)
        set_bag(game, FULL_BAG)
        game.write("wListPointer", game.address("wNumBagItems").to_bytes(2, "little"))
        game.write("wListMenuID", 3)  # ITEMLISTMENU
        game.write("wCurrentMenuItem", 2)
        game.write("wListScrollOffset", 37)
        game.write("wMenuItemToSwap", 1)  # slot 1, with slot 40 selected
        stub(game, "DelayFrames")
        stub(game, "DisplayListMenuIDLoop")
        game.call("HandleItemListSwapping")
        expected = FULL_BAG.copy()
        expected[0], expected[-1] = expected[-1], expected[0]
        check_bag(game, expected)
        # Combining two matching slots must close the gap beyond slot 20.
        expected[20] = (1, 2)
        expected[39] = (1, 3)
        set_bag(game, expected)
        game.write("wMenuItemToSwap", 21)
        game.call("HandleItemListSwapping")
        expected[39] = (1, 5)
        expected.pop(20)
        check_bag(game, expected)
    finally:
        game.stop()


def check_new_game(fixed, save):
    game = Game(fixed, save)
    try:
        ready, started = [], []
        def menu_ready(_):
            stack = game.emulator.register_file.SP
            caller = game.memory[stack] | game.memory[stack + 1] << 8
            if game.address("MainMenu") <= caller < game.address("InitOptions"):
                ready.append(True)
        game.emulator.hook_register(*game.symbols["HandleMenuInput"], menu_ready, None)
        game.emulator.hook_register(*game.symbols["StartNewGame"], lambda _: started.append(True), None)
        game.open_main_menu()
        for _ in range(600):
            if ready:
                break
            game.emulator.tick(1, False)
        assert ready, "Main menu did not wait for input"
        for _ in range(10):
            if game.read("wCurrentMenuItem") == b"\x01":
                break
            game.emulator.button("down")  # New Game, below Continue
            game.emulator.tick(12, False)
        assert game.read("wCurrentMenuItem") == b"\x01", "New Game was not selected"
        game.emulator.button("a")
        game.wait_for("OverworldLoop", button="a")
        assert started, "New Game did not start"
        check_bag(game, [])
        assert game.read("wBagSaveVersion", 4) == b"BAG\x01"
        assert add(game, 0x14)
        check_bag(game, [(0x14, 1)])
    finally:
        game.stop()


def check_capture_save(fixed, save):
    prepared, boxes = fixture(fixed, save, 0, [20, 19] + [20] * 10)
    game = Game(fixed, prepared)
    try:
        load(game)
        quiet_interface(game)
        set_bag(game, FULL_BAG)
        game.call("SaveSAVtoSRAM")
        before = cartridge_ram(game)
        game.write("wIsInBattle", 1)
        game.write("wcf91", 1)
        game.write("wWhichPokemon", 39)
        game.write("wEnemyMonSpecies2", 0x99)
        game.write("wCurEnemyLevel", 10)
        game.call("LoadEnemyMonData")
        game.call("ItemUseBall")
        expected = FULL_BAG.copy()
        expected[-1] = (1, expected[-1][1] - 1)
        check_bag(game, expected)
        assert game.read("wCapturedMonSpecies") == b"\x99"
        assert game.read("wAutoBoxChangePending") != b"\x00"
        reset = Game(fixed, cartridge_ram(game))
        try:
            load(reset)
            check_bag(reset, FULL_BAG)
            assert read_saved_boxes(reset) == boxes
        finally:
            reset.stop()
        game.write("wIsInBattle", 0)
        game.call("FinishAutoBoxChange")
        assert cartridge_ram(game) != before
        updated = cartridge_ram(game)
    finally:
        game.stop()
    reloaded = Game(fixed, updated)
    try:
        load(reloaded)
        check_bag(reloaded, expected)
        assert reloaded.read("wCurrentBoxNum") == b"\x81"
        assert reloaded.read("wBoxCount") == b"\x14"
    finally:
        reloaded.stop()


def check_larger_save(larger, fixed):
    game = Game(larger)
    try:
        game.open_main_menu()
        game.wait_for("OverworldLoop", button="a")
        items = [(item, 2) for item in ALL_ITEMS[:59]] + [(1, 3)]
        set_bag(game, items)
        game.call("SaveSAVtoSRAM")
        save = game.stop(save=True)
    finally:
        game.stop()
    game = Game(fixed, save)
    try:
        load(game)
        check_bag(game, items)
        assert not add(game, 0xC9), "An overfull old bag accepted a new slot"
        assert add(game, 1), "An overfull old bag rejected an existing stack"
        items[-1] = (1, 4)
        check_bag(game, items)
        game.call("SaveSAVtoSRAM")
        saved = cartridge_ram(game)
        reloaded = Game(fixed, saved)
        try:
            load(reloaded)
            check_bag(reloaded, items)
        finally:
            reloaded.stop()
        while len(items) > 39:
            remove(game, len(items) - 1, items[-1][1])
            items.pop()
        assert add(game, 0xC9)
        items.append((0xC9, 1))
        check_bag(game, items)
        assert not add(game, 0xCA), "Bag exceeded 40 slots after reducing an old bag"
    finally:
        game.stop()


def check_color(original, previous, larger, fixed, color):
    check_old_saves(original, fixed)
    check_old_saves(previous, fixed)
    save, _, _ = make_official_save(original)
    check_inventory(fixed, save)
    full = check_full_save(fixed, save)
    check_swapping(fixed, save)
    check_new_game(fixed, full)
    check_capture_save(fixed, save)
    check_playthrough(fixed, save, bag_bytes(FULL_BAG))
    check_larger_save(larger, fixed)
    print(f"{color}: old saves import; 40 slots, stack limits, removal, gifts, "
          "PC limit, Continue, automatic saves, and real battle menus passed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dir", type=Path, required=True)
    parser.add_argument("--previous-dir", type=Path, required=True)
    parser.add_argument("--larger-bag-dir", type=Path, required=True)
    parser.add_argument("--fixed-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    for color in ("red", "green", "blue"):
        name = f"pokesolus{color}.gbc"
        check_color(args.original_dir / name, args.previous_dir / name,
                    args.larger_bag_dir / name, args.fixed_dir / name, color)
