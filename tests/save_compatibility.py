#!/usr/bin/env python3
"""Check official Solus 1.5 saves against the fixed ROMs with PyBoy 2.8.1."""

import argparse
from io import BytesIO
from pathlib import Path
from zlib import crc32

from pyboy import PyBoy

from critical_hits import read_symbols


ORIGINAL_CRC32 = {"red": 0x4D0B49CB, "green": 0x22B4EFD5, "blue": 0x031E86E5}
PARTY = [(0x68, 50, "JOLTEON"), (0xB4, 36, "CHARIZARD"),
         (0x95, 42, "ALAKAZAM"), (0x84, 30, "SNORLAX"),
         (0x16, 55, "GYARADOS"), (0x42, 60, "DRAGONITE")]


class Game:
    def __init__(self, rom, save=None):
        self.symbols = read_symbols(rom.with_suffix(".sym"))
        self.emulator = PyBoy(str(rom), ram_file=BytesIO(save or b"\xff" * 32768),
                              window="null", sound_emulated=False)
        self.emulator.set_emulation_speed(0)
        self.memory = self.emulator.memory
        self.driver_installed = False

    def address(self, name):
        return self.symbols[name][1]

    def read(self, name, length=1):
        start = self.address(name)
        return bytes(self.memory[start:start + length])

    def write(self, name, data):
        if isinstance(data, int):
            data = bytes([data])
        start = self.address(name)
        self.memory[start:start + len(data)] = data

    def region(self, start, end):
        return self.read(start, self.address(end) - self.address(start))

    def snapshot(self):
        return {
            "name": self.read("wPlayerName", 11),
            "main": self.region("wMainDataStart", "wMainDataEnd"),
            "sprites": self.region("wSpriteDataStart", "wSpriteDataEnd"),
            "party": self.region("wPartyDataStart", "wPartyDataEnd"),
            "box": self.region("wBoxDataStart", "wBoxDataEnd"),
            "tiles": self.read("hTileAnimations"),
        }

    def wait_for(self, name, frames=6000, button=None):
        reached = []
        self.emulator.hook_register(*self.symbols[name], lambda _: reached.append(True), None)
        try:
            for _ in range(frames // 30):
                if button:
                    self.emulator.button(button)
                self.emulator.tick(30, False)
                if reached:
                    return
            raise AssertionError(f"Did not reach {name}")
        finally:
            self.emulator.hook_deregister(*self.symbols[name])

    def open_main_menu(self):
        self.wait_for("DisplayTitleScreen.awaitUserInterruptionLoop")
        self.emulator.button("start")
        self.wait_for("MainMenu.mainMenuLoop", frames=600)

    def call(self, name, **registers):
        # Call unmodified game routines through a driver in the emulator's ROM
        # copy. Nothing is written to the source ROM or to a user's save file.
        emulator = self.emulator
        memory = self.memory
        if not self.driver_installed:
            memory[0, 0x104] = 0x00
            emulator.hook_register(0, 0x104, self.returned, None)
            self.driver_installed = True
        self.result = None
        bank, entry = self.symbols[name]
        memory[0, 0x100:0x104] = [0xF3, 0xCD, entry & 0xFF, entry >> 8]
        memory[0, 0x105:0x108] = [0xC3, 0x04, 0x01]
        memory[0xFF50] = 1
        memory[0xFFFF] = 0
        memory[0xFF40] = 0
        memory[0xFF07] = 0
        memory[0x2000] = bank or 1
        self.write("hLoadedROMBank", bank or 1)
        emulator.register_file.SP = 0xDFFF
        emulator.register_file.PC = 0x100
        for register, value in registers.items():
            setattr(emulator.register_file, register, value)
        for _ in range(100):
            emulator.tick(1, False)
            if self.result is not None:
                return self.result
        raise AssertionError(f"{name} did not return")

    def returned(self, _):
        if self.result is None:
            self.result = self.emulator.register_file.F

    def stop(self, save=False):
        data = BytesIO()
        self.emulator.stop(save=save, ram_file=data)
        return data.getvalue()


def encoded_name(name):
    return bytes([ord(letter) - ord("A") + 0x80 for letter in name]).ljust(11, b"\x50")


def check_snapshot(actual, expected, stage):
    differences = {name: [index for index, (left, right) in enumerate(zip(data, actual[name]))
                          if left != right][:12]
                   for name, data in expected.items() if data != actual[name]}
    assert not differences, f"{stage}: saved fields differ at byte offsets {differences}"


def make_box(game, number):
    size = game.address("wBoxDataEnd") - game.address("wBoxDataStart")
    data = bytearray(size)
    count = 20 if number in (1, 12) else 0 if number == 6 else number % 3 + 1
    data[0] = count
    data[1:count + 1] = bytes(PARTY[index % 6][0] for index in range(count))
    data[count + 1] = 0xFF
    for index in range(count):
        slot = index % 6 + 1
        for field, length, source in (("wBoxMon1", 33, f"wPartyMon{slot}"),
                                      ("wBoxMon1OT", 11, f"wPartyMon{slot}OT"),
                                      ("wBoxMon1Nick", 11, f"wPartyMon{slot}Nick")):
            offset = game.address(field) - game.address("wBoxDataStart") + index * length
            data[offset:offset + length] = game.read(source, length)
    return bytes(data)


def make_official_save(rom):
    game = Game(rom)
    try:
        game.open_main_menu()
        game.wait_for("OverworldLoop", button="a")  # new game and default names
        for slot, (species, level, name) in enumerate(PARTY, 1):
            game.write("wcf91", species)
            game.write("wCurEnemyLevel", level)
            game.write("wMonDataLocation", 0x10)  # player party, no naming prompt
            assert game.call("AddPartyMon") & 0x10, "Could not create test party"
            game.write(f"wPartyMon{slot}Nick", encoded_name(name))
        game.write("wNumBagItems", 3)
        game.write("wBagItems", bytes([0x14, 7, 0x04, 50, 0x06, 1, 0xFF]))
        game.write("wNumBoxItems", 2)
        game.write("wBoxItems", bytes([0x11, 8, 0x4B, 1, 0xFF]))
        game.write("wPlayerMoney", bytes([0x12, 0x34, 0x56]))
        game.write("wObtainedBadges", 0xA5)
        # Starter, rival battle, Poké Balls, and Pokédex progress flags.
        game.memory[game.address("wEventFlags") + 4] |= 0x3C
        game.write("wPlayTimeHours", 123)
        game.write("wPlayTimeMinutes", 45)
        game.write("wPlayTimeSeconds", 11)
        game.write("wPlayTimeFrames", 0)
        game.call("EmptyAllSRAMBoxes")
        boxes = [make_box(game, number) for number in range(1, 13)]
        for number, data in enumerate(boxes, 1):
            game.write("wBoxDataStart", data)
            bank, target = game.symbols[f"sBox{number}"]
            game.call("CopyBoxToOrFromSRAM", HL=game.address("wBoxDataStart"),
                      D=target >> 8, E=target & 0xFF, B=bank)
        # Load Box 7 as the active box, just as the Change Box menu does.
        game.write("wCurrentBoxNum", 0x86)
        bank, source = game.symbols["sBox7"]
        target = game.address("wBoxDataStart")
        game.call("CopyBoxToOrFromSRAM", HL=source, D=target >> 8, E=target & 0xFF, B=bank)
        game.call("SaveSAVtoSRAM")
        snapshot = game.snapshot()
        save = game.stop(save=True)
        assert len(save) == 32768
        return save, snapshot, boxes
    finally:
        game.stop()


def check_load_and_save(rom, save, expected):
    game = Game(rom, save)
    try:
        for name in ("LoadSAV0", "LoadSAV1", "LoadSAV2"):
            assert not game.call(name) & 0x10, f"{name}: save checksum rejected"
        check_snapshot(game.snapshot(), expected, "Load")
        game.call("SaveSAVtoSRAM")
        return game.stop(save=True)
    finally:
        game.stop()


def check_boxes(rom, save, boxes):
    game = Game(rom, save)
    try:
        for name in ("LoadSAV0", "LoadSAV1", "LoadSAV2"):
            assert not game.call(name) & 0x10
        for number, expected in enumerate(boxes):
            # Store the active box, then load the next one with the game's own
            # routines. This covers empty and full boxes in both SRAM banks.
            game.call("GetBoxSRAMLocation")
            registers = game.emulator.register_file
            target = registers.HL
            game.call("CopyBoxToOrFromSRAM", HL=game.address("wBoxDataStart"),
                      D=target >> 8, E=target & 0xFF)
            game.write("wCurrentBoxNum", 0x80 | number)
            game.call("GetBoxSRAMLocation")
            target = game.address("wBoxDataStart")
            game.call("CopyBoxToOrFromSRAM", D=target >> 8, E=target & 0xFF)
            assert game.region("wBoxDataStart", "wBoxDataEnd") == expected, f"Box {number + 1} changed"
    finally:
        game.stop()


def check_continue(rom, save, expected):
    game = Game(rom, save)
    try:
        # Capture saved fields at the first menu loop, before menu setup can
        # change flags or the game clock can advance.
        snapshots = []
        bank, address = game.symbols["MainMenu.mainMenuLoop"]
        game.emulator.hook_register(bank, address, lambda _: snapshots.append(game.snapshot()), None)
        game.wait_for("DisplayTitleScreen.awaitUserInterruptionLoop")
        game.emulator.button("start")
        for _ in range(20):
            game.emulator.tick(30, False)
            if snapshots:
                break
        game.emulator.hook_deregister(bank, address)
        assert snapshots, "Continue menu was not reached"
        # The running game clock can advance a few frames after the load. Keep
        # checking its hours, minutes, and seconds, but allow the frame counter.
        actual = snapshots[0]
        main = bytearray(actual["main"])
        frame = game.address("wPlayTimeFrames") - game.address("wMainDataStart")
        assert main[frame] < 60, "Invalid play-time frame counter"
        main[frame] = expected["main"][frame]
        actual["main"] = bytes(main)
        check_snapshot(actual, expected, "Continue menu")
        assert game.read("wSaveFileStatus") == b"\x02", "Continue did not recognize the save"
        game.wait_for("OverworldLoop", frames=900, button="a")
        assert game.read("wPartyCount") == b"\x06"
        assert game.region("wPartyDataStart", "wPartyDataEnd") == expected["party"]
        assert game.region("wBoxDataStart", "wBoxDataEnd") == expected["box"]
        for name, length in (("wCurMap", 1), ("wYCoord", 1), ("wXCoord", 1),
                             ("wBagItems", 7), ("wBoxItems", 5), ("wPlayerMoney", 3),
                             ("wObtainedBadges", 1), ("wEventFlags", 320),
                             ("wPokedexOwned", 19), ("wPokedexSeen", 19)):
            offset = game.address(name) - game.address("wMainDataStart")
            assert game.read(name, length) == expected["main"][offset:offset + length], name
    finally:
        game.stop()


def check_color(original, fixed, color):
    original_bytes = original.read_bytes()
    fixed_bytes = fixed.read_bytes()
    assert crc32(original_bytes) == ORIGINAL_CRC32[color], "Input must be official Solus 1.5"
    assert original_bytes[0x143:0x14D] == fixed_bytes[0x143:0x14D], "Cartridge settings changed"
    old_symbols = read_symbols(original.with_suffix(".sym"))
    new_symbols = read_symbols(fixed.with_suffix(".sym"))
    ram_symbols = {name: value for name, value in old_symbols.items() if value[1] >= 0x8000}
    assert ram_symbols == {name: value for name, value in new_symbols.items() if value[1] >= 0x8000}
    # The complete ROM bank that holds the save/load and PC box routines must
    # also match, including their machine code and called addresses.
    bank = old_symbols["LoadSAV"][0]
    assert original_bytes[bank * 0x4000:(bank + 1) * 0x4000] == fixed_bytes[bank * 0x4000:(bank + 1) * 0x4000]
    save, expected, boxes = make_official_save(original)
    # LoadSAV0 always sets the map tileset's high bit, including in the official
    # ROM. Account for that documented loader behavior in the expected data.
    data = bytearray(expected["main"])
    data[new_symbols["wCurMapTileset"][1] - new_symbols["wMainDataStart"][1]] |= 0x80
    expected["main"] = bytes(data)
    original_resave = check_load_and_save(original, save, expected)
    fixed_resave = check_load_and_save(fixed, save, expected)
    assert original_resave == fixed_resave, "Saving changed cartridge RAM contents"
    assert check_load_and_save(original, fixed_resave, expected) == fixed_resave
    assert check_load_and_save(fixed, fixed_resave, expected) == fixed_resave
    check_boxes(fixed, save, boxes)
    check_continue(fixed, save, expected)
    check_continue(fixed, fixed_resave, expected)
    print(f"{color}: {len(ram_symbols):,} RAM labels unchanged; official save loads, "
          "all 12 boxes work, 32 KiB resave matches, and Continue works before and after saving")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dir", type=Path, required=True,
                        help="Directory with official 1.5 ROMs and matching .sym files")
    parser.add_argument("--fixed-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    for color in ORIGINAL_CRC32:
        check_color(args.original_dir / f"pokesolus{color}.gbc",
                    args.fixed_dir / f"pokesolus{color}.gbc", color)
