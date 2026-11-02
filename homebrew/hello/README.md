# Original NX2Apple homebrew

This original MIT-licensed program contains no Nintendo SDK or retail game content.
The generator writes a small unencrypted NSO and NPDM from the format definitions,
not from a console dump. All bootstrap functions are original return stubs. `nnMain`
prints a diagnostic through Horizon SVC 0x27, sleeps for one second with SVC 0x0b,
then repeats. The upstream rewriter must replace both SVC sites.

The undefined, unused `vkCreateInstance` metadata symbol selects upstream's Vulkan
shader build route. It has no relocation and is never called. The original vertex
and fragment shaders exercise GLSL → SPIR-V → MSL → Metal library compilation and
packaging. The CPU program does not draw a triangle or validate graphics at runtime.

`homebrew_ipa.py` runs the actual `engine/scripts/build_ipa_from_nsp.py` dump-folder
route, including RomFS packing, registered build-ID checks, NSO rewriting, shader
translation, host compilation and IPA packaging. It does not test NSP/XCI extraction,
decryption, retail profiles or NVN shader translation.

The IPA is deliberately named NX2Apple Homebrew Test and uses its own bundle ID.
It contains the homebrew's complete tiny RomFS. No external data transfer is needed.
Before public upload, font resources are replaced with the repository's OFL Manrope font
and a button font generated from it. The OFL and engine/third-party license notices
are included. No system font is redistributed.

Cloud build and archive verification are separate from signing, installation and
execution. The IPA has no Apple provisioning profile or developer signature.
After signing and installing it, the guest message in the app's Documents/log.txt is
the evidence that rewritten guest code actually executed. A blank game view alone
is not a runtime pass.

On-device validation on an M4 iPad Pro running iPadOS 27.0.1 found that a 256 MiB
address-space reservation fails the host's native boundary check. The host reserves
the first 256 MiB before adding the alias region, stacks and heap. This fixture now
reserves 512 MiB of virtual address space, leaving 188 MiB for its 128 MiB application
pool after the 64 MiB alias and 4 MiB stack regions. Pages are committed on demand.
The installed build was retested with the equivalent `DM_PROF_MEM_RESERVE=0x20000000`
override and produced repeated guest messages without the reported Play-time crash.
This confirms CPU guest execution for this fixture. It does not validate runtime
graphics, retail games or the rebuilt IPA's installation on every device.
