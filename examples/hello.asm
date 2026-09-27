;******************************************************************************
; hello.asm - the smallest tft4 program: a title, the 16 palette colors, a
; sprite and a line of text, sent to the panel with one LcdPresent.
; Project: tft4.asm + tft4_config.inc + font6x8.asm + this file.
;******************************************************************************
	.cdecls C,LIST,"msp430.h"
	.def    RESET
	.ref    ClockInit, LcdInit, LcdPresent, LcdWait
	.ref    FbClear, FbFillRect, FbText, FbBlit
	.global __STACK_END
	.sect   .stack

	.sect   ".const"
Title	.byte   "Hello, tft4!", 0
Colors	.byte   "16 colors:", 0
Heart	.byte   7, 6                    ; sprite: width 7, height 6, then the
	.byte   0x08, 0x80, 0x88, 0x00  ; rows, 2 pixels per byte, 4 bytes per
	.byte   0x88, 0x88, 0x88, 0x80  ; row (7 pixels + 1 padding):
	.byte   0x88, 0x88, 0x88, 0x80  ;   .88.88.   8 = red
	.byte   0x08, 0x88, 0x88, 0x00  ;   8888888   0 = transparent
	.byte   0x00, 0x88, 0x80, 0x00  ;   ..888..
	.byte   0x00, 0x08, 0x00, 0x00  ;   ...8...
	.align  2

	.text
	.retain
	.retainrefs
RESET	mov.w   #__STACK_END, SP
	mov.w   #WDTPW+WDTHOLD, &WDTCTL
	call    #ClockInit              ; 16 MHz
	bic.w   #LOCKLPM5, &PM5CTL0
	call    #LcdInit

	mov.w   #1, R12                 ; navy background
	call    #FbClear

	mov.w   #Title, R12             ; yellow text, no background
	mov.w   #28, R13
	mov.w   #10, R14
	mov.w   #10+0xFF00, R15         ; color 10 + (background 255 << 8)
	call    #FbText

	mov.w   #Colors, R12
	mov.w   #4, R13
	mov.w   #40, R14
	mov.w   #7+0xFF00, R15
	call    #FbText

	clr.w   R4                      ; 16 swatches (R4 = color; R4 survives
Swatch	mov.w   R4, R12                 ; every driver call)
	rla.w   R12                     ; x = color * 8
	rla.w   R12
	rla.w   R12
	mov.w   #52, R13
	mov.w   #0x0C07, R14            ; w = 7, h = 12
	mov.w   R4, R15
	call    #FbFillRect
	inc.w   R4
	cmp.w   #16, R4
	jlo     Swatch

	mov.w   #Heart, R12             ; the sprite, 3 times
	mov.w   #50, R13
	mov.w   #80, R14
	call    #FbBlit
	mov.w   #Heart, R12
	mov.w   #60, R13
	mov.w   #80, R14
	call    #FbBlit
	mov.w   #Heart, R12
	mov.w   #70, R13
	mov.w   #80, R14
	call    #FbBlit

	call    #LcdPresent             ; send it
	call    #LcdWait
Done	bis.w   #CPUOFF+OSCOFF+SCG0+SCG1, SR ; LPM4: nothing else to do
	jmp     Done

	.sect   ".reset"
	.short  RESET
	.end
