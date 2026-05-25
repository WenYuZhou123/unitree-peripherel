from setuptools import setup

package_name = "inspection_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", ["launch/bench.launch.py"]),
        (
            f"share/{package_name}/config",
            [
                "config/alarm.yaml",
                "config/cameras.yaml",
                "config/env.yaml",
                "config/thermal.yaml",
            ],
        ),
        (
            f"share/{package_name}/docs",
            ["docs/b2_migration.md", "docs/udev_rules.example"],
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="wyz",
    maintainer_email="wyz@example.com",
    description="Launch and configuration assets for inspection peripherals.",
    license="Apache-2.0",
)
