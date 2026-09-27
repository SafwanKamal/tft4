INCLUDE msp430fr6989_symbols.ld
MEMORY { RAM (rwx) : ORIGIN = 0x1C00, LENGTH = 0x0800
         FRAM (rx) : ORIGIN = 0x4400, LENGTH = 0xBB00 }
SECTIONS {
  .rodata : { *(.rodata*) } > FRAM
  .text   : { *(.text*) }   > FRAM
  .data   : { *(.data*) }   > RAM
  .bss (NOLOAD) : { *(.bss*) *(COMMON) } > RAM
}
