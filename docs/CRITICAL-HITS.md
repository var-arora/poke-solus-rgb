# Critical-hit fix for Solus 1.5

This fork restores Gen 1's normal critical-hit rates. Focus Energy then
quadruples the chance, up to 255/256 (about 99.6%). The fix applies to both sides
of a battle and all three colors of Solus.

## Download and apply a patch

Choose one patch for your input ROM. Each row produces the same fixed ROM for
that color. A patcher that supports BPS checks the input ROM before applying it.

| Version | Input: clean original ROM | Input: official Solus 1.5 ROM |
| --- | --- | --- |
| Red | [Red patch](../patches/critical-hit-fix/pokesolusred-1.5-crit-fix.bps), for Pokémon Red | [Red update](../patches/critical-hit-fix/pokesolusred-1.5-to-crit-fix.bps) |
| Green | [Green patch](../patches/critical-hit-fix/pokesolusgreen-1.5-crit-fix.bps), for Pokémon Red | [Green update](../patches/critical-hit-fix/pokesolusgreen-1.5-to-crit-fix.bps) |
| Blue | [Blue patch](../patches/critical-hit-fix/pokesolusblue-1.5-crit-fix.bps), for Pokémon Blue | [Blue update](../patches/critical-hit-fix/pokesolusblue-1.5-to-crit-fix.bps) |

Download the file with GitHub's **Download raw file** button. Apply it with
[Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) or
[Floating IPS](https://github.com/Alcaro/Flips). Open the output ROM in your emulator.

The clean-ROM patches require these SHA-1 hashes:

- Pokémon Red: `ea9bcae617fdf159b045185467ae58b2e4a48b9a`
- Pokémon Blue: `d7037c83e1ae5b39bde3c30787637ba1d4c48ce2`

The Solus update patches require these CRC32 checksums:

- Solus Red 1.5: `4d0b49cb`
- Solus Green 1.5: `22b4efd5`
- Solus Blue 1.5: `031e86e5`

All input and output ROMs are 1,048,576 bytes. These patches do not target other
Solus releases or ROMs with additional changes. Patch-file SHA-256 checksums are
in [SHA256SUMS](../patches/critical-hit-fix/SHA256SUMS).

The save-data layout is unchanged. To continue a game, back up your in-game
save file and give it the same base filename as the fixed ROM, as required by
your emulator. Loading an existing save or emulator save state was not tested.

## What changed

In upstream Solus, `CriticalHitTest` first halves the species' base Speed.
Without Focus Energy, it halves the value again. An ordinary move then halves
it once more. The result is `floor(base Speed / 8)`, instead of Gen 1's
`floor(base Speed / 2)`. Focus Energy in upstream Solus returns ordinary moves
to the normal Gen 1 rate.

This fork starts with `floor(base Speed / 2)` and removes the extra divisions.
High-critical-hit moves multiply that value by 8. Focus Energy multiplies the
result by 4. Both boosts cap the value at 255.

The resulting chance is:

```text
threshold = floor(species base Speed / 2)
if the move is Karate Chop, Razor Leaf, Crabhammer, or Slash:
    threshold = min(threshold * 8, 255)
if Focus Energy is active:
    threshold = min(threshold * 4, 255)
critical-hit chance = threshold / 256
```

This uses the species' base Speed, not the Pokémon's current Speed stat.
Moves with zero base power still return without a critical hit. The random
number generator and damage calculation are unchanged.

For example, Jolteon has base Speed 130. Its ordinary moves have these chances:

| Build | Without Focus Energy | With Focus Energy |
| --- | --- | --- |
| Official Solus 1.5 | 16/256 (6.25%) | 65/256 (25.39%) |
| This fork | 65/256 (25.39%) | 255/256 (99.61%) |

The original Solus change is
[commit d8e77838](https://github.com/Dechrissen/poke-solus-rgb/commit/d8e7783828c70e646c4fab52a80cc089ae996ed5).
The corrected calculation is in
[`engine/battle/core.asm`](../engine/battle/core.asm).

## Build and test

Use RGBDS 0.8.0, the version selected by upstream's build workflow:

```sh
make -j8 red blue green
python3 -m venv /tmp/solus-critical-hit-tests
/tmp/solus-critical-hit-tests/bin/pip install -r tests/requirements.txt
/tmp/solus-critical-hit-tests/bin/python tests/critical_hits.py \
    pokesolusred.gbc pokesolusgreen.gbc pokesolusblue.gbc
```

The test runs the compiled `CriticalHitTest` routine in PyBoy. It supplies each
possible base Speed and random byte at the header-loader and random-generator
calls. It checks both battle sides, Focus Energy on and off, an ordinary move,
and all four high-critical-hit moves. It also checks zero-power moves, unrelated
status bits, and clearing a previous critical-hit flag. The test changes only
the emulator's ROM copy; it does not edit the ROM file on disk.

Each color passes 1,312,768 checks. The same test rejects unmodified Solus 1.5.
The fixed ROMs also pass a normal boot through the title screen and main menu.
These checks do not replace a full playthrough.

The unmodified source at upstream commit `95e15719` builds byte-for-byte matches
for all three official 1.5 release ROMs. Applying each new patch to its stated
input was checked against the corresponding fixed build, byte for byte.

| Fixed ROM | CRC32 | SHA-256 |
| --- | --- | --- |
| Red | `df7b71b6` | `7cb8a6c0b22b0dce54d7e57e610111e513bb0a3d63a1215239abb52d45f32250` |
| Green | `86ccaecd` | `2acba067e8cd4aad6f2e0bb54b667d2210014bdda29fc1f27bae70277ad3b1b6` |
| Blue | `3545034f` | `fb606961f263e9b255abb0eda12d7172f6c721656ee7d6fae6bbc77145c221ae` |

To recreate the Red patches with Floating IPS, first build the fixed ROM and
provide matching clean Red and official Solus Red 1.5 input ROMs:

```sh
flips --create --bps clean-red.gbc pokesolusred.gbc \
    patches/critical-hit-fix/pokesolusred-1.5-crit-fix.bps
flips --create --bps official-solus-red-1.5.gbc pokesolusred.gbc \
    patches/critical-hit-fix/pokesolusred-1.5-to-crit-fix.bps
```
