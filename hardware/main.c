/******************************************************************************
* File Name:   main.c
*
* Description: Thie source code illustrates how to start with DSP on Infineon µC
*
* Related Document: See README.md
*
*
*  Created on: 2026-02-05
*  Company: Rutronik Elektronische Bauelemente GmbH
*  Author: ROJ030, GDR
*
*******************************************************************************
* (c) 2019-2021, Cypress Semiconductor Corporation. All rights reserved.
*******************************************************************************
* This software, including source code, documentation and related materials
* ("Software"), is owned by Cypress Semiconductor Corporation or one of its
* subsidiaries ("Cypress") and is protected by and subject to worldwide patent
* protection (United States and foreign), United States copyright laws and
* international treaty provisions. Therefore, you may use this Software only
* as provided in the license agreement accompanying the software package from
* which you obtained this Software ("EULA").
*
* If no EULA applies, Cypress hereby grants you a personal, non-exclusive,
* non-transferable license to copy, modify, and compile the Software source
* code solely for use in connection with Cypress's integrated circuit products.
* Any reproduction, modification, translation, compilation, or representation
* of this Software except as specified above is prohibited without the express
* written permission of Cypress.
*
* Disclaimer: THIS SOFTWARE IS PROVIDED AS-IS, WITH NO WARRANTY OF ANY KIND,
* EXPRESS OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, NONINFRINGEMENT, IMPLIED
* WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. Cypress
* reserves the right to make changes to the Software without notice. Cypress
* does not assume any liability arising out of the application or use of the
* Software or any product or circuit described in the Software. Cypress does
* not authorize its products for use in any products where a malfunction or
* failure of the Cypress product may reasonably be expected to result in
* significant property damage, injury or death ("High Risk Product"). By
* including Cypress's product in a High Risk Product, the manufacturer of such
* system or application assumes all risk of such use and in doing so agrees to
* indemnify Cypress against all liability.
*
* Rutronik Elektronische Bauelemente GmbH Disclaimer: The evaluation board
* including the software is for testing purposes only and,
* because it has limited functions and limited resilience, is not suitable
* for permanent use under real conditions. If the evaluation board is
* nevertheless used under real conditions, this is done at one’s responsibility;
* any liability of Rutronik is insofar excluded
*******************************************************************************/

#include "cyhal.h"
#include "cybsp.h"
#include "cy_retarget_io.h"

// Access to the BGT60TR13C API (configure, start frame, ...)
#include <xensiv_bgt60trxx_mtb.h>

// Access to the radar settings exported using the Radar Fusion GUI
#define XENSIV_BGT60TRXX_CONF_IMPL
#include <math.h>
#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif
#define SPEED_OF_LIGHT_MPS        (299792458.0f)

/* Tune these */
#define MIN_TARGET_BIN           (1)        // was 2 — allows ~2.7 cm minimum
#define MAX_TARGET_BIN           (XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP / 2)       // 16 = full usable spectrum at 32 samples
#define DETECTION_THRESHOLD      (0.02f)    // was 0.20 — start low, tune later
#define RANGE_BIN_LENGTH_M       (0.0273f)  // unchanged: c / (2 * 5.5GHz)
#include "radar_settings.h"

// Access to DSP library
// Have a look to the documentation of Sensor-DSP to see all possible functions
#include "ifx_sensor_dsp.h"

// Compute how many samples a frame contains
#define NUM_SAMPLES_PER_FRAME (XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP \
		* XENSIV_BGT60TRXX_CONF_NUM_CHIRPS_PER_FRAME \
		* XENSIV_BGT60TRXX_CONF_NUM_RX_ANTENNAS)

// Communication mechanism between ISR and main function
static uint16_t data_available = 0;

// SPI frequency used to communicate with the radar
#define XENSIV_BGT60TRXX_SPI_FREQUENCY      (25000000UL)

/**
 * @brief Interrupt service routine called when radar values (a frame) are available
 *
 * See xensiv_bgt60trxx_mtb_interrupt_init
 */
void radar_isr(void *args, cyhal_gpio_event_t event)
{
    CY_UNUSED_PARAMETER(args);
    CY_UNUSED_PARAMETER(event);

    // Values are available, then can be read using the function xensiv_bgt60trxx_get_fifo_data
    data_available = 1;
}

/**
 * @brief Initialize the SPI block that will be used for the communication
 * with the radar sensor
 *
 * @retval true on success
 */
static bool _init_spi(cyhal_spi_t* spi)
{
    if (cyhal_spi_init(spi,
    		CYBSP_RSPI_MOSI,
            CYBSP_RSPI_MISO,
            CYBSP_RSPI_CLK,
            NC,
            NULL,
            8,
            CYHAL_SPI_MODE_00_MSB,
            false) != CY_RSLT_SUCCESS)
    {
        printf("[MSG] ERROR: cyhal_spi_init failed\r\n");
        return false;
    }

    // Reduce drive strength to improve EMI
    Cy_GPIO_SetSlewRate(CYHAL_GET_PORTADDR(CYBSP_RSPI_MOSI), CYHAL_GET_PIN(CYBSP_RSPI_MOSI), CY_GPIO_SLEW_FAST);
	Cy_GPIO_SetDriveSel(CYHAL_GET_PORTADDR(CYBSP_RSPI_MOSI), CYHAL_GET_PIN(CYBSP_RSPI_MOSI), CY_GPIO_DRIVE_1_8);
	Cy_GPIO_SetSlewRate(CYHAL_GET_PORTADDR(CYBSP_RSPI_CLK), CYHAL_GET_PIN(CYBSP_RSPI_CLK), CY_GPIO_SLEW_FAST);
	Cy_GPIO_SetDriveSel(CYHAL_GET_PORTADDR(CYBSP_RSPI_CLK), CYHAL_GET_PIN(CYBSP_RSPI_CLK), CY_GPIO_DRIVE_1_8);

    // Set the data rate to 25 Mbps
    if (cyhal_spi_set_frequency(spi, XENSIV_BGT60TRXX_SPI_FREQUENCY) != CY_RSLT_SUCCESS)
    {
        printf("[MSG] ERROR: cyhal_spi_set_frequency failed\r\n");
        return false;
    }

    return true;
}

static bool _init_bgt60tr13c(cyhal_spi_t* spi, xensiv_bgt60trxx_mtb_t* bgt60_obj)
{
    // Wait LDO stable
    cyhal_system_delay_ms(5);

    if (xensiv_bgt60trxx_mtb_init(bgt60_obj,
                                  spi,
								  CYBSP_RSPI_CS,
								  CYBSP_RXRES_L,
								  register_list,
								  XENSIV_BGT60TRXX_CONF_NUM_REGS) != CY_RSLT_SUCCESS)
    {
        printf("[MSG] ERROR: xensiv_bgt60trxx_mtb_init failed\n");
        return false;
    }

	// The sensor will generate an interrupt once the sensor FIFO level is NUM_SAMPLES_PER_FRAME
	if (xensiv_bgt60trxx_mtb_interrupt_init(bgt60_obj,
			NUM_SAMPLES_PER_FRAME,
			CYBSP_RSPI_IRQ,
			CYHAL_ISR_PRIORITY_DEFAULT,
			radar_isr,
			NULL) != CY_RSLT_SUCCESS)
    {
    	printf("ERROR: xensiv_bgt60trxx_mtb_interrupt_init\r\n");
    	return false;
    }

    return true;
}

/**
 * @brief Main function
 *
 * Initializes the system, start radar frame generation and process the frame
 */
int main(void)
{
	cyhal_spi_t spi;
	xensiv_bgt60trxx_mtb_t bgt60_obj;

    // Initialize the device and board peripherals
    if (cybsp_init() != CY_RSLT_SUCCESS)
    {
    	CY_ASSERT(0);
    }

    // Initialize retarget-io for uart logs
    if (cy_retarget_io_init(CYBSP_DEBUG_UART_TX,
    		CYBSP_DEBUG_UART_RX,
			CY_RETARGET_IO_BAUDRATE) != CY_RSLT_SUCCESS)
    {
    	CY_ASSERT(0);
    }


    // \x1b[2J\x1b[;H - ANSI ESC sequence for clear screen
    printf("\x1b[2J\x1b[;H");

    printf("*************** "
           "Rutronik - CY8CKIT_062S2_AI - Radar DSP basis project."
           "*************** \r\n\n");

    // Initialize GPIOs
    cyhal_gpio_init(CYBSP_USER_LED1, CYHAL_GPIO_DIR_OUTPUT, CYHAL_GPIO_DRIVE_STRONG, false);
    cyhal_gpio_init(CYBSP_USER_LED2, CYHAL_GPIO_DIR_OUTPUT, CYHAL_GPIO_DRIVE_STRONG, false);

    // Enable interrupts
    // Needs before call to _init_bgt60tr13c (since SPI needs it)
    __enable_irq();

    // Init SPI bus (needed to configure and collect radar data)
    if (!_init_spi(&spi))
    {
    	printf("Cannot initialize SPI\r\n");
    	return -1;
    }

    // Init the radar sensor
    if (!_init_bgt60tr13c(&spi, &bgt60_obj))
    {
    	printf("Cannot initialize radar BGT60TR13C\r\n");
    	return -1;
    }

    // Start the frame generation
    if(xensiv_bgt60trxx_start_frame(&bgt60_obj.dev, true) != XENSIV_BGT60TRXX_STATUS_OK)
	{
		printf("Cannot start frame\r\n");
		return -1;
	}

    printf("Radar configured and initialized. Frames are beeing generated.\r\n");
	printf("FW_VERSION: RANGE_TEST_V2_MINBIN5\r\n");
    // Buffer used to store 1 frame coming from the radar
    uint16_t radar_raw_values[NUM_SAMPLES_PER_FRAME];

    // Buffer used to store the first chirp
    float first_chirp[XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP];

    static arm_rfft_fast_instance_f32 rfft = { 0 };
    arm_rfft_fast_init_f32(&rfft, XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP);

    cfloat32_t range[XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP / 2];

    /* Pre-compute Hann window once at startup */
    float hann_window[XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP];
    for (int i = 0; i < XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP; i++)
    {
        hann_window[i] = 0.5f * (1.0f - cosf(2.0f * (float)M_PI * i /
                         (XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP - 1)));
    }

    /* Buffer for averaged magnitude spectrum across all chirps */
    float avg_magnitude[XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP / 2];

    for(;;)
    {
    	// Data available from the radar
    	if (data_available)
    	{
    		data_available = 0;
    		if (xensiv_bgt60trxx_get_fifo_data(&bgt60_obj.dev, radar_raw_values, NUM_SAMPLES_PER_FRAME) != XENSIV_BGT60TRXX_STATUS_OK)
			{
				printf("xensiv_bgt60trxx_get_fifo_data error\r\n");
				xensiv_bgt60trxx_start_frame(&bgt60_obj.dev, false);
				cyhal_system_delay_ms(5);
				xensiv_bgt60trxx_start_frame(&bgt60_obj.dev, true);
				continue;
			}

    		/* Zero the average accumulator */
            const int N = XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP;
            const int NA = XENSIV_BGT60TRXX_CONF_NUM_RX_ANTENNAS;
            const int NUM_CHIRPS = XENSIV_BGT60TRXX_CONF_NUM_CHIRPS_PER_FRAME;

            for (int b = 0; b < N / 2; b++)
            {
                avg_magnitude[b] = 0.0f;
            }

            /* Process all chirps from antenna 0, accumulate magnitude spectra */
            for (int chirp = 0; chirp < NUM_CHIRPS; chirp++)
            {
                /* 1. Extract this chirp from antenna 0 and compute mean */
                float mean = 0.0f;
                for (int i = 0; i < N; i++)
                {
                    /* Frame layout: [chirp][sample][antenna] */
                    int idx = (chirp * N * NA) + (i * NA);  // antenna 0
                    first_chirp[i] = (float)radar_raw_values[idx] / 4095.0f;
                    mean += first_chirp[i];
                }
                mean /= (float)N;

                /* 2. Subtract DC offset and apply Hann window */
                for (int i = 0; i < N; i++)
                {
                    first_chirp[i] = (first_chirp[i] - mean) * hann_window[i];
                }

                /* 3. Compute range FFT */
                arm_rfft_fast_f32(&rfft, first_chirp, (float32_t*)range, 0);

                /* 4. Accumulate magnitude (skip bin 0 — it's DC) */
                for (int b = 1; b < N / 2; b++)
                {
                    float re = CREAL_F32(range[b]);
                    float im = CIMAG_F32(range[b]);
                    avg_magnitude[b] += sqrtf(re * re + im * im);
                }
            }

            /* Normalize the averaged spectrum */
            for (int b = 1; b < N / 2; b++)
            {
                avg_magnitude[b] /= (float)NUM_CHIRPS;
            }

            /* Find peak in the valid window */
            float max_mag = 0.0f;
            int max_index = -1;
            int last_bin = (N / 2 < MAX_TARGET_BIN) ? (N / 2) : MAX_TARGET_BIN;

            for (int i = MIN_TARGET_BIN; i < last_bin; i++)
            {
                if (avg_magnitude[i] > DETECTION_THRESHOLD &&
                    avg_magnitude[i] > max_mag)
                {
                    max_mag = avg_magnitude[i];
                    max_index = i;
                }
            }

            /* Print result every ~5 frames (~9 Hz at 45 Hz frame rate) */
            static uint32_t print_counter = 0;
            print_counter++;
            if (print_counter >= 5)
            {
                print_counter = 0;

                /* DEBUG: dump full spectrum so we can pick a real threshold */
                printf("SPEC");
                for (int b = 1; b < N / 2; b++)
                {
                    printf(",%.4f", avg_magnitude[b]);
                }
                printf("\r\n");

                if (max_index >= 0)
                {
                    float distance_m = max_index * RANGE_BIN_LENGTH_M;
                    printf("TARGET,%.3f,%d,%.3f\r\n",
                           distance_m, max_index, max_mag);
                }
                else
                {
                    printf("NO_TARGET\r\n");
                }
            } /* end if (print_counter >= 5) */

            cyhal_gpio_toggle(CYBSP_USER_LED1);
        } /* end if (data_available) */
    } /* end for(;;) */
} /* end main() */
/* [] END OF FILE */
