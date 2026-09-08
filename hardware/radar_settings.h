#ifndef XENSIV_BGT60TRXX_CONF_H
#define XENSIV_BGT60TRXX_CONF_H

/*
 * Generated configuration for BGT60TR13C
 *   Samples per chirp:  128 (was 32) -> ~174 cm max range
 *   Chirps per frame:   32
 *   Frame rate:         ~25 Hz (40 ms repetition)
 *   Bandwidth:          5.5 GHz (58 -> 63.5 GHz)
 *   Range resolution:   2.73 cm
 */

#define XENSIV_BGT60TRXX_CONF_DEVICE (XENSIV_DEVICE_BGT60TR13C)
#define XENSIV_BGT60TRXX_CONF_START_FREQ_HZ (58000000000)
#define XENSIV_BGT60TRXX_CONF_END_FREQ_HZ (63500000000)
#define XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP (128)
#define XENSIV_BGT60TRXX_CONF_NUM_CHIRPS_PER_FRAME (32)
#define XENSIV_BGT60TRXX_CONF_NUM_RX_ANTENNAS (3)
#define XENSIV_BGT60TRXX_CONF_NUM_TX_ANTENNAS (1)
#define XENSIV_BGT60TRXX_CONF_SAMPLE_RATE (2000000)
#define XENSIV_BGT60TRXX_CONF_CHIRP_REPETITION_TIME_S (0.0005911)
#define XENSIV_BGT60TRXX_CONF_FRAME_REPETITION_TIME_S (0.0400294)
#define XENSIV_BGT60TRXX_CONF_NUM_REGS (38)

#if defined(XENSIV_BGT60TRXX_CONF_IMPL)
const uint32_t register_list[] = {
    0x011e8270UL,    /* MAIN     0x00 */
    0x030a0210UL,    /* ADC0     0x01 */
    0x09e967fdUL,    /* PACR1    0x04 */
    0x0b0805b4UL,    /* PACR2    0x05 */
    0x0d1027ffUL,    /* SFCTL    0x06 */
    0x0f010700UL,    /* SADC_CTRL 0x07 */
    0x11000000UL,    /* CSP_I_0  0x08 */
    0x13000000UL,    /* CSP_I_1  0x09 */
    0x15000000UL,    /* CSP_I_2  0x0a */
    0x17000be0UL,    /* CSCI     0x0b */
    0x19000000UL,    /* CSP_D_0  0x0c */
    0x1b000000UL,    /* CSP_D_1  0x0d */
    0x1d000000UL,    /* CSP_D_2  0x0e */
    0x1f000b60UL,    /* CSCDS    0x0f */
    0x2113fc51UL,    /* CS1_U_0  0x10 */
    0x237ff41fUL,    /* CS1_U_1  0x11 */
    0x25701ce7UL,    /* CS1_U_2  0x12 */
    0x2d000490UL,    /* CS1      0x16 */
    0x3b000480UL,    /* CS2      0x1d */
    0x49000480UL,    /* CS3      0x24 */
    0x57000480UL,    /* CS4      0x2b */
    0x5911be0eUL,    /* CCR0     0x2c */
    0x5b564c0aUL,    /* CCR1     0x2d */
    0x5d01f000UL,    /* CCR2     0x2e */
    0x5f787e1eUL,    /* CCR3     0x2f */
    0x61a628ccUL,    /* PLL1_0   0x30 */
    0x6300068eUL,    /* PLL1_1   0x31 */
    0x650002b2UL,    /* PLL1_2   0x32 */
    0x67000080UL,    /* PLL1_3   0x33 -- APU_LEN=128 (samples per chirp) */
    0x69000000UL,    /* PLL1_4   0x34 */
    0x6b000000UL,    /* PLL1_5   0x35 */
    0x6d000000UL,    /* PLL1_6   0x36 */
    0x6f324b10UL,    /* PLL1_7   0x37 */
    0x7f000100UL,    /* PLL2_7   0x3f */
    0x8f000100UL,    /* PLL3_7   0x47 */
    0x9f000100UL,    /* PLL4_7   0x4f */
    0xad000000UL,    /* RFT1     0x56 */
    0xb7000000UL,    /* SDFT0    0x5b */
};
#endif /* XENSIV_BGT60TRXX_CONF_IMPL */

#endif /* XENSIV_BGT60TRXX_CONF_H */
