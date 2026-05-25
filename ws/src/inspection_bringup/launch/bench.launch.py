from pathlib import Path

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import LogInfo, OpaqueFunction
from launch_ros.actions import Node


CAMERAS = [
    ("front", "/dev/v4l/by-id/cam_front"),
    ("rear", "/dev/v4l/by-id/cam_rear"),
    ("left", "/dev/v4l/by-id/cam_left"),
    ("right", "/dev/v4l/by-id/cam_right"),
]


def _camera_actions():
    try:
        get_package_share_directory("v4l2_camera")
        use_v4l2 = True
    except PackageNotFoundError:
        use_v4l2 = False

    actions = []
    for name, device in CAMERAS:
        namespace = f"cam/{name}"
        if use_v4l2:
            actions.append(
                Node(
                    package="v4l2_camera",
                    executable="v4l2_camera_node",
                    name=f"{name}_camera",
                    namespace=namespace,
                    parameters=[
                        {
                            "video_device": device,
                            "image_size": [1280, 720],
                            "time_per_frame": [1, 15],
                            "pixel_format": "mjpeg",
                            "camera_frame_id": f"{name}_camera_optical_frame",
                        }
                    ],
                    output="screen",
                )
            )
        else:
            actions.append(
                Node(
                    package="inspection_vision",
                    executable="camera_placeholder",
                    name=f"{name}_camera_placeholder",
                    namespace=namespace,
                    parameters=[
                        {
                            "width": 1280,
                            "height": 720,
                            "fps": 15.0,
                            "frame_id": f"{name}_camera_optical_frame",
                            "label": name,
                        }
                    ],
                    output="screen",
                )
            )

    if not use_v4l2:
        actions.insert(
            0,
            LogInfo(
                msg=(
                    "Package 'v4l2_camera' not found. Starting camera placeholder "
                    "publishers instead of hardware-backed USB camera nodes."
                )
            ),
        )

    return actions


def _launch_setup(context, *args, **kwargs):
    del context, args, kwargs
    share_dir = Path(get_package_share_directory("inspection_bringup"))

    actions = [
        Node(
            package="inspection_vision",
            executable="thermal_bridge",
            name="thermal_bridge",
            parameters=[str(share_dir / "config" / "thermal.yaml")],
            output="screen",
        ),
        Node(
            package="inspection_env",
            executable="env_bridge",
            name="env_bridge",
            parameters=[str(share_dir / "config" / "env.yaml")],
            output="screen",
        ),
        Node(
            package="inspection_alarm",
            executable="alarm_controller",
            name="alarm_controller",
            parameters=[str(share_dir / "config" / "alarm.yaml")],
            output="screen",
        ),
    ]
    actions.extend(_camera_actions())
    return actions


def generate_launch_description():
    return LaunchDescription([OpaqueFunction(function=_launch_setup)])
