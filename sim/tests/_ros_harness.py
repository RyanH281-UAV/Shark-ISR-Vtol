"""Shared rclpy lifecycle for the SITL test scripts.

Spins the node in a joinable executor thread and tears it down in the right
order (executor.shutdown -> join -> destroy_node -> try_shutdown) so the
process exits with the test body's return code and never aborts with SIGABRT
from a daemon spin thread racing context finalization.
"""
import threading

import rclpy
from rclpy.executors import SingleThreadedExecutor


def run(node_name: str, body) -> int:
    rclpy.init()
    node = rclpy.create_node(node_name)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    spin = threading.Thread(target=ex.spin)
    spin.start()
    try:
        return body(node)
    finally:
        ex.shutdown()       # signals ex.spin() to return
        spin.join(timeout=2)
        node.destroy_node()
        rclpy.try_shutdown()
