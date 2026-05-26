from setuptools import find_packages, setup

package_name = 'crawler_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/bringup.launch.py']),
        ('share/' + package_name + '/config', ['config/config.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Andre Arante',
    maintainer_email='andrearante12@gmail.com',
    description='UDP/TCP messaging bridge between the Pi-Crawler and ROS 2.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'udp_telemetry_node = crawler_bridge.udp_telemetry_node:main',
            'cmd_bridge_node = crawler_bridge.cmd_bridge_node:main',
        ],
    },
)
