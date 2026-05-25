# B2 Migration Notes

## Network

- Keep ROS 2 topic and service names unchanged.
- Reserve one USB-to-Ethernet adapter for a dedicated bench or maintenance link.
- Match the final `ROS_DOMAIN_ID` and subnet to the B2 deployment environment before field tests.

## Power and Wiring

- Move 12V/24V loads off the Jetson bench supply and onto the B2-approved power rail.
- Keep the alarm digital-output controller isolated from the main compute GPIOs.
- Use the `8+2` adapter only as the physical breakout; do not change application-layer topics.

## Software

- Reuse `inspection_bringup` launch files and replace only device paths and IP addresses.
- Keep hardware-specific protocol code inside the bridge nodes so migration does not affect upstream consumers.
