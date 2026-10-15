# Gameplay fixes for Solus 1.5

This build includes two fixes:

- Normal critical-hit rates match Gen 1. Focus Energy quadruples those rates,
  up to 255/256 (about 99.6%).
- Effectiveness messages and hit sounds use the combined result against both
  defending types. A weakness and resistance that cancel give no effectiveness
  message and use the normal hit sound.

The game still supports the original Game Boy. Its CGB header flag is `00`.
The source build keeps upstream's `.gbc` filenames; a byte-identical copy can
use `.gb` without changing the game.

## Download a patch

Choose the column that matches your input ROM. Every patch in a row produces
the same updated ROM for that color. All inputs and outputs are 1,048,576 bytes.

| Version | Clean original ROM | Official Solus 1.5 | Earlier critical-hit fix |
| --- | --- | --- | --- |
| Red | [Red patch](../patches/gameplay-fixes/pokesolusred-1.5-gameplay-fixes.bps), for Pokémon Red | [Red update](../patches/gameplay-fixes/pokesolusred-1.5-to-gameplay-fixes.bps) | [Red update](../patches/gameplay-fixes/pokesolusred-crit-fix-to-gameplay-fixes.bps) |
| Green | [Green patch](../patches/gameplay-fixes/pokesolusgreen-1.5-gameplay-fixes.bps), for Pokémon Red | [Green update](../patches/gameplay-fixes/pokesolusgreen-1.5-to-gameplay-fixes.bps) | [Green update](../patches/gameplay-fixes/pokesolusgreen-crit-fix-to-gameplay-fixes.bps) |
| Blue | [Blue patch](../patches/gameplay-fixes/pokesolusblue-1.5-gameplay-fixes.bps), for Pokémon Blue | [Blue update](../patches/gameplay-fixes/pokesolusblue-1.5-to-gameplay-fixes.bps) | [Blue update](../patches/gameplay-fixes/pokesolusblue-crit-fix-to-gameplay-fixes.bps) |

Download the patch with GitHub's **Download raw file** button. Apply it with
[Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) or
[Floating IPS](https://github.com/Alcaro/Flips). BPS patchers check that the input
ROM matches. Do not apply more than one patch from a row.

Input ROM checksums:

| Input | Red | Green | Blue |
| --- | --- | --- | --- |
| Clean original ROM, SHA-1 | `ea9bcae617fdf159b045185467ae58b2e4a48b9a` | Same as Red | `d7037c83e1ae5b39bde3c30787637ba1d4c48ce2` |
| Official Solus 1.5, CRC32 | `4d0b49cb` | `22b4efd5` | `031e86e5` |
| Earlier critical-hit fix, CRC32 | `df7b71b6` | `86ccaecd` | `3545034f` |

Patch-file SHA-256 checksums are in
[SHA256SUMS](../patches/gameplay-fixes/SHA256SUMS).

## Continue a saved game

Existing Solus 1.5 in-game saves remain compatible, including saves made with
the earlier critical-hit fix. The save layout, cartridge settings, and compiled
save/load routines are unchanged.

1. Make an in-game save in your current ROM.
2. Back up the save file, usually a `.sav` file.
3. Replace or patch the ROM. Keep its base filename the same as the save file,
   or import the save with your emulator's save-file option.
4. Start the updated ROM and choose **Continue**.

Emulator save states store the running game and its code addresses. They are
separate from in-game saves and are not covered by these compatibility checks.
Use an in-game save when changing ROM versions.

## Effectiveness reporting

The original routine applies each type modifier to damage, but overwrites the
reported effectiveness with each matching entry in the type chart. Messages
and hit sounds therefore use the last matching entry, even when the two types
cancel each other.

The fix combines the reporting value while keeping the damage calculation and
its rounding unchanged. The same-type attack bonus remains separate from type
effectiveness. An immunity keeps the combined result at zero.

| Attack type | Defending types | Combined result | Message | Hit sound |
| --- | --- | --- | --- | --- |
| Fighting | Normal / Flying | 1× | None | Normal |
| Grass | Water / Poison | 1× | None | Normal |
| Ice | Water / Flying | 1× | None | Normal |
| Fire | Bug / Grass | 4× | Super effective | Super effective |
| Fire | Water / Rock | ¼× | Not very effective | Not very effective |
| Electric | Water / Ground | 0× | Doesn't affect | None |
| Ground | Bug / Flying | 0× | Doesn't affect | None |

Single-type defenders are counted once. Reversing the order of a defender's
types does not change its reported effectiveness. The existing type chart is
unchanged, including Solus's Ghost-versus-Psychic fix.

The calculation is in
[`AdjustDamageForMoveType`](../engine/battle/core.asm). Both
[`DisplayEffectiveness`](../engine/battle/display_effectiveness.asm) and
[`PlayApplyingAttackSound`](../engine/battle/animations.asm) already read the
same reporting value, so they both receive the corrected result.

For details of the critical-hit calculation, see the
[critical-hit fix guide](CRITICAL-HITS.md#what-changed).

## Build and test

Use RGBDS 0.8.0, then build the ROMs and install the test tools:

```sh
make -j8 red blue green
python3 -m venv /tmp/solus-tests
/tmp/solus-tests/bin/pip install -r tests/requirements.txt
```

Build unmodified upstream commit
`95e157191e920162a24908cc95c358e73d294689` in a separate directory with the same
RGBDS version. Keep its `.sym` files beside its ROMs. Run:

```sh
/tmp/solus-tests/bin/python tests/type_effectiveness.py \
    --original-dir /path/to/unmodified-solus-build
/tmp/solus-tests/bin/python tests/critical_hits.py \
    pokesolusred.gbc pokesolusgreen.gbc pokesolusblue.gbc
/tmp/solus-tests/bin/python tests/save_compatibility.py \
    --original-dir /path/to/unmodified-solus-build
```

The effectiveness test runs the compiled damage-adjustment, message-selection,
and hit-sound routines. It checks all 15 attack types against every ordered pair
of the 15 defending types, including single-type pairs. It covers both battle
sides, no same-type attack bonus, a bonus from either attacker type, and seven
starting damage values from 2 to 999. Each color passes 141,750 damage and
effectiveness cases. Damage, miss flags, and the same-type attack bonus are
compared with the unmodified ROM. The type chart must also match.

Another 28 cases per color check the message and hit-sound selectors for each
combined effectiveness value, both battle sides, and the same-type bonus flag
on and off. Printing and audio playback are replaced with test hooks that
inspect the selected text, sound ID, frequency, and tempo. The original damage
math runs unchanged inside the emulator. The test edits only the emulator's
private ROM copy.

The critical-hit tests and disposable-save checks also pass for all three
colors. They cover party data, items, money, badges, progress, all 12 PC boxes,
and continuing before and after saving again. Each patch was applied to its
stated input and checked against the built ROM, byte for byte.

| Updated ROM | CRC32 | SHA-256 |
| --- | --- | --- |
| Red | `24743609` | `fe75bdf4c4e67e458aca108079c229faeb52cdef0271f104ca6d9ac4a7eca46c` |
| Green | `f5452102` | `439c11a8b509b0609c5af4d1e45de9cf9cae362d8ef7d741e978db0a7b7a5bad` |
| Blue | `a921c774` | `369fd6c8d354800a76a126c058ee121c9459d17b793119126b9e7280e760062f` |
