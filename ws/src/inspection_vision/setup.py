from setuptools import setup

package_name = "inspection_vision"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools", "numpy", "pyserial"],
    zip_safe=True,
    maintainer="wyz",
    maintainer_email="wyz@example.com",
    description="Vision nodes for camera and thermal bridge scaffolding.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "camera_placeholder = inspection_vision.camera_placeholder:main",
            "thermal_bridge = inspection_vision.thermal_bridge:main",
        ]
    },
)
