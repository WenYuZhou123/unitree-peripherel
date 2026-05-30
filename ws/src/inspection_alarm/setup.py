from setuptools import setup

package_name = "inspection_alarm"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools", "pyserial"],
    zip_safe=True,
    maintainer="wyz",
    maintainer_email="wyz@example.com",
    description="Alarm controller scaffolding.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "alarm_controller = inspection_alarm.alarm_controller:main",
            "relay_cli = inspection_alarm.relay_cli:main",
        ]
    },
)
