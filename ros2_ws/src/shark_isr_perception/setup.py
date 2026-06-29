from setuptools import setup
import os
from glob import glob

package_name = 'shark_isr_perception'

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
    maintainer_email='you@example.com',
    description='Camera Module 3 ingest + Hailo-8L shark detector + geolocation.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mock_camera_node = shark_isr_perception.mock_camera_node:main',
            'detector_node = shark_isr_perception.detector_node:main',
        ],
    },
)
