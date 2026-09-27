/* Make clang --target=msp430 accept TI-compiler-only syntax for a compile check. */
#define __TI_COMPILER_VERSION__ 21006001
#define __interrupt
void __delay_cycles(unsigned long);
unsigned short __get_SR_register(void);
void __bis_SR_register(unsigned short);
void __bic_SR_register(unsigned short);
void __bic_SR_register_on_exit(unsigned short);
void __enable_interrupt(void);
void __disable_interrupt(void);
void __no_operation(void);
#define __IN430_H__
#define __INTRINSICS_H__
