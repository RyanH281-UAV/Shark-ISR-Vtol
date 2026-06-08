from setuptools import setup
import os
from glob import glob

package_name = 'shark_isr_autopilot'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Ryan Hughes',
    maintainer_email='ryanhughes281@yahoo.com',
    description='PX4 autopilot bridge — the only package talking to the autopilot.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'autopilot_bridge = shark_isr_autopilot.autopilot_bridge:main',
        ],
    },
)
