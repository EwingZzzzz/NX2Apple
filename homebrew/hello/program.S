// SPDX-License-Identifier: MIT
// Original CPU-only Horizon-ABI homebrew. No Nintendo SDK code.
// The generator encodes these instructions directly into an unencrypted NSO.
// Bootstrap exports are RET stubs. nnMain emits one message each second.
.global nnMain
nnMain:
    adr x0, message
    mov x1, #message_length
    svc #0x27
    movz x0, #0xca00
    movk x0, #0x3b9a, lsl #16
    svc #0x0b
    b nnMain
message:
    .ascii "NX2Apple original homebrew: rewritten guest code is running"
message_end:
.equ message_length, message_end - message
