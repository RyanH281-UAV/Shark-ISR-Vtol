cmake_minimum_required(VERSION 3.8)
project(shark_isr_interfaces)

find_package(ament_cmake REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Detection.msg"
  "msg/GuidanceSetpoint.msg"
  "msg/SearchState.msg"
  "msg/VehicleState.msg"
  "srv/AutopilotCommand.srv"
  "srv/MissionCommand.srv"
  "srv/SetGuidanceMode.srv"
  DEPENDENCIES std_msgs geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
