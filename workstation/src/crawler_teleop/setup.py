from setuptools import find_packages, setup

package_name = 'crawler_teleop'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Andre Arante',
    maintainer_email='andrearante12@gmail.com',
    description='Keyboard teleop for Pi-Crawler.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'teleop_keyboard_node = crawler_teleop.teleop_keyboard_node:main',
        ],
    },
)
