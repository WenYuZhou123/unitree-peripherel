#include "stm32f10x.h"                  // Device header
#include "OLED.h"
#include "Relay.h"
#include "Serial.h"

#define CMD_SET_ONE				0x01
#define CMD_SET_ALL				0x02
#define CMD_QUERY_STATE			0x03

#define STATUS_OK				0x00
#define STATUS_CHECKSUM_ERROR	0x01
#define STATUS_INVALID_CMD		0x02
#define STATUS_INVALID_CHANNEL	0x03
#define STATUS_INVALID_STATE	0x04

static uint8_t Main_CalcChecksum(uint8_t byte0, uint8_t byte1, uint8_t byte2)
{
	return byte0 ^ byte1 ^ byte2;
}

static void Main_ShowRelayState(uint8_t state_mask)
{
	OLED_ShowChar(2, 1, (state_mask & 0x01) ? '1' : '0');
	OLED_ShowChar(2, 4, (state_mask & 0x02) ? '1' : '0');
	OLED_ShowChar(2, 7, (state_mask & 0x04) ? '1' : '0');
}

static void Main_ShowLastFrame(uint8_t cmd, uint8_t status, uint8_t state_mask)
{
	OLED_ShowString(3, 1, "C:00 S:00");
	OLED_ShowString(4, 1, "M:00");
	OLED_ShowHexNum(3, 3, cmd, 2);
	OLED_ShowHexNum(3, 8, status, 2);
	OLED_ShowHexNum(4, 3, state_mask, 2);
}

int main(void)
{
	OLED_Init();
	Relay_Init();
	Serial_Init();
	
	OLED_ShowString(1, 1, "R1 R2 R3");
	Main_ShowRelayState(Relay_GetStateMask());
	Main_ShowLastFrame(0x00, STATUS_OK, Relay_GetStateMask());
	
	while (1)
	{
		if (Serial_GetRxFlag() == 1)
		{
			uint8_t cmd = Serial_RxPacket[0];
			uint8_t arg1 = Serial_RxPacket[1];
			uint8_t arg2 = Serial_RxPacket[2];
			uint8_t checksum = Serial_RxPacket[3];
			uint8_t status = STATUS_OK;
			uint8_t state_mask = Relay_GetStateMask();
			
			if (checksum != Main_CalcChecksum(cmd, arg1, arg2))
			{
				status = STATUS_CHECKSUM_ERROR;
			}
			else if (cmd == CMD_SET_ONE)
			{
				if (arg1 < 1 || arg1 > 3)
				{
					status = STATUS_INVALID_CHANNEL;
				}
				else if (arg2 > 1)
				{
					status = STATUS_INVALID_STATE;
				}
				else
				{
					Relay_SetChannel(arg1, arg2);
					state_mask = Relay_GetStateMask();
				}
			}
			else if (cmd == CMD_SET_ALL)
			{
				Relay_SetAll(arg1);
				state_mask = Relay_GetStateMask();
			}
			else if (cmd == CMD_QUERY_STATE)
			{
				state_mask = Relay_GetStateMask();
			}
			else
			{
				status = STATUS_INVALID_CMD;
			}
			
			state_mask = Relay_GetStateMask();
			Serial_SendFrame(cmd, status, state_mask);
			Main_ShowRelayState(state_mask);
			Main_ShowLastFrame(cmd, status, state_mask);
		}
	}
}
