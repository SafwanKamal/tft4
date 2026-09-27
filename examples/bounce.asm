;******************************************************************************
; bounce.asm - retained mode: the scenery is drawn once and saved (FbSaveBg);
; every frame only erases the ball (FbRestoreSpr), moves it and draws it
; again. LcdPresent then sends just the pixels around the ball.
; Project: tft4.asm + tft4_config.inc + font6x8.asm + this file.
;
; R6/R7 = speed x/y, R8/R9 = ball x/y (R4-R10 survive every driver call)
;******************************************************************************
	.cdecls C,LIST,"msp430.h"
	.include "tft4_config.inc"      ; CLOCK_MHZ, for the frame timer
	.def    RESET
	.ref    ClockInit, LcdInit, LcdPresent, LcdPresentFull, LcdWait
	.ref    FbClear, FbFillRect, FbBlit, FbSaveBg, FbRestoreSpr
	.global __STACK_END
	.sect   .stack

	.sect   ".const"
Ball	.byte   6, 6                    ; 6 x 6, 3 bytes per row
	.byte   0x0A, 0xA9, 0x00        ;   .AA9..   A = yellow
	.byte   0xAA, 0xA9, 0x90        ;   AAA99.   9 = orange
	.byte   0xAA, 0x99, 0x90        ;   AA999.
	.byte   0xA9, 0x99, 0x80        ;   A9998.   8 = red
	.byte   0x09, 0x98, 0x00        ;   .998..
	.byte   0x00, 0x00, 0x00        ;   ......
	.align  2

	.text
	.retain
	.retainrefs
RESET	mov.w   #__STACK_END, SP
	mov.w   #WDTPW+WDTHOLD, &WDTCTL
	call    #ClockInit
	bic.w   #LOCKLPM5, &PM5CTL0
	; 25 Hz frame tick: SMCLK / 8 / (CLOCK_MHZ / 8) = 1 MHz, / 40000
	mov.w   #CLOCK_MHZ/8-1, &TA0EX0
	mov.w   #40000-1, &TA0CCR0
	mov.w   #TASSEL__SMCLK+ID__8+MC__UP+TACLR, &TA0CTL
	call    #LcdInit

	; scenery, once: sky, ground, a wall
	mov.w   #12, R12                ; sky blue
	call    #FbClear
	clr.w   R12
	mov.w   #108, R13
	mov.w   #0x1480, R14            ; 128 x 20
	mov.w   #3, R15                 ; dark green
	call    #FbFillRect
	mov.w   #60, R12
	mov.w   #70, R13
	mov.w   #0x2608, R14            ; 8 x 38
	mov.w   #4, R15                 ; brown
	call    #FbFillRect
	call    #FbSaveBg               ; remember it: erasing restores from here
	call    #LcdPresentFull

	mov.w   #10, R8                 ; ball
	mov.w   #20, R9
	mov.w   #2, R6
	mov.w   #1, R7

Frame	bit.w   #CCIFG, &TA0CCTL0       ; wait for the tick
	jz      Frame
	bic.w   #CCIFG, &TA0CCTL0

	mov.w   #Ball, R12              ; erase at the old place
	mov.w   R8, R13
	mov.w   R9, R14
	call    #FbRestoreSpr

	add.w   R6, R8                  ; move, bounce off the edges and the ground
	cmp.w   #122, R8
	jl      ChkLeft
	xor.w   #0xFFFF, R6
	inc.w   R6
ChkLeft	cmp.w   #1, R8
	jge     MoveY
	xor.w   #0xFFFF, R6
	inc.w   R6
MoveY	add.w   R7, R9
	cmp.w   #102, R9
	jl      ChkTop
	xor.w   #0xFFFF, R7
	inc.w   R7
ChkTop	cmp.w   #1, R9
	jge     Draw
	xor.w   #0xFFFF, R7
	inc.w   R7

Draw	mov.w   #Ball, R12              ; draw at the new place
	mov.w   R8, R13
	mov.w   R9, R14
	call    #FbBlit
	call    #LcdPresent             ; ~0.2 ms: only the ball's pixels
	call    #LcdWait
	jmp     Frame

	.sect   ".reset"
	.short  RESET
	.end
