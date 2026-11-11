FROM ros:jazzy-ros-core-noble

RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    python3-numpy \
    python3-opencv \
    ros-jazzy-cv-bridge \
    ros-jazzy-rclpy \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-sensor-msgs \
    ros-jazzy-std-msgs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/ros-entrypoint.sh
ENV PYTHONUNBUFFERED=1 \
    RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    CYCLONEDDS_URI=file:///tmp/cyclonedds.xml \
    ROS_AUTOMATIC_DISCOVERY_RANGE=SYSTEM_DEFAULT
# Validate generated XML with the installed middleware, without needing a VPN.
RUN /bin/bash -c 'source /opt/ros/jazzy/setup.bash && python3 /app/scripts/check_dds.py'
ENTRYPOINT ["/app/scripts/ros-entrypoint.sh"]
