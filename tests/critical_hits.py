#!/usr/bin/env python3
"""Check the compiled critical-hit routine with PyBoy 2.8.1."""

import argparse
from itertools import product
from pathlib import Path

from pyboy import PyBoy


def read_symbols(path):
    symbols = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith(";"):
            continue
        location, name = line.split()
        bank, address = location.split(":")
        symbols[name] = (int(bank, 16), int(address, 16))
    return symbols


def check_rom(rom):
    symbols = read_symbols(rom.with_suffix(".sym"))
    emulator = PyBoy(str(rom), window="null", sound_emulated=False)
    emulator.set_emulation_speed(0)
    memory = emulator.memory
    registers = emulator.register_file

    def address(name):
        return symbols[name][1]

    # Run the actual routine from a small driver in this emulator's ROM copy.
    # Replace only the species-header loader and random generator with returns.
    # Hooks supply every possible base Speed and random byte at those calls.
    bank, entry = symbols["CriticalHitTest"]
    driver = [0xF3, 0xCD, entry & 0xFF, entry >> 8, 0x00, 0xC3, 0x01, 0x01]
    memory[0, 0x100:0x108] = driver
    for name in ("GetMonHeader", "BattleRandom"):
        hook_bank, hook_address = symbols[name]
        memory[hook_bank, hook_address] = 0xC9  # ret

    memory[0xFF50] = 1  # disable boot ROM
    memory[0xFFFF] = 0  # disable interrupts
    memory[0xFF40] = 0  # disable LCD
    memory[0xFF07] = 0  # disable timer
    memory[0x2000] = bank
    memory[address("hLoadedROMBank")] = bank
    registers.PC = 0x100
    registers.SP = 0xDFFF

    # Tackle and all four high-critical-hit moves, followed by zero-power moves.
    moves = [(33, 40, 1), (2, 50, 8), (75, 55, 8), (152, 90, 8), (163, 70, 8),
             (116, 0, 1), (163, 0, 8)]
    scenarios = iter(product(range(256), range(2), range(2), moves))
    state = {"done": False, "checks": 0, "rolls": 0}

    def next_scenario():
        try:
            speed, side, focus, (move, power, multiplier) = next(scenarios)
        except StopIteration:
            state["done"] = True
            memory[0, 0x105:0x108] = [0x76, 0x18, 0xFD]  # halt; jr back
            return
        state.update(speed=speed, side=side, focus=focus, power=power, random=0,
                     threshold=min((speed // 2) * multiplier * (4 if focus else 1), 255))
        memory[address("hWhoseTurn")] = side
        memory[address("wBattleMonSpecies")] = 0x99  # Bulbasaur
        memory[address("wEnemyMonSpecies")] = 0xB0  # Charmander
        active = "Enemy" if side else "Player"
        inactive = "Player" if side else "Enemy"
        memory[address(f"w{active}MoveNum")] = move
        memory[address(f"w{active}MovePower")] = power
        memory[address(f"w{active}BattleStatus2")] = 0xFF if focus else 0xFB
        # Give the other side different data to catch use of the wrong fields.
        memory[address(f"w{inactive}MoveNum")] = 163 if multiplier == 1 else 33
        memory[address(f"w{inactive}MovePower")] = 0 if power else 40
        memory[address(f"w{inactive}BattleStatus2")] = 0xFB if focus else 0xFF
        memory[address("wCriticalHitOrOHKO")] = 1  # must clear a stale flag

    def supply_header(_):
        expected_species = 0xB0 if state["side"] else 0x99
        assert memory[address("wd0b5")] == expected_species, state
        memory[address("wMonHBaseSpeed")] = state["speed"]

    def supply_random(_):
        assert state["power"], "Zero-power move reached the random generator"
        assert registers.B == state["threshold"], dict(state, actual=registers.B)
        registers.A = state["random"]
        state["rolls"] += 1

    def check_result(_):
        random_byte = state["random"]
        rotated = ((random_byte << 3) | (random_byte >> 5)) & 0xFF
        expected = int(bool(state["power"]) and rotated < state["threshold"])
        actual = memory[address("wCriticalHitOrOHKO")]
        assert actual == expected, dict(state, expected=expected, actual=actual)
        state["checks"] += 1
        if random_byte == 255 or not state["power"]:
            next_scenario()
        else:
            state["random"] += 1
            memory[address("wCriticalHitOrOHKO")] = 1

    def guarded(callback):
        # PyBoy can swallow exceptions raised inside hooks. Save the error and
        # raise it after tick() returns so a failed check exits with an error.
        def hook(context):
            if state["done"]:
                return
            try:
                callback(context)
            except Exception as error:
                state["error"] = error
                state["done"] = True
                memory[0, 0x105:0x108] = [0x76, 0x18, 0xFD]
        return hook

    emulator.hook_register(*symbols["GetMonHeader"], guarded(supply_header), None)
    emulator.hook_register(*symbols["BattleRandom"], guarded(supply_random), None)
    emulator.hook_register(0, 0x104, guarded(check_result), None)
    next_scenario()
    try:
        for _ in range(100000):
            emulator.tick(1, False)
            if state["done"]:
                break
        if "error" in state:
            raise state["error"]
        assert state["done"], "Critical-hit checks did not finish"
        assert state["checks"] == 1_312_768, state
        assert state["rolls"] == 1_310_720, state
    finally:
        emulator.stop(save=False)
    print(f"{rom.name}: {state['checks']:,} compiled-routine checks passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roms", type=Path, nargs="+", help="Built ROMs with adjacent .sym files")
    for rom_path in parser.parse_args().roms:
        check_rom(rom_path)
