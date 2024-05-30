#!/bin/bash

######
# This script is for use with Samuel's IP (de)obfuscation scripts. It has three requirements:
# 1. it must be run as root;
# 2. it only works from within the Internet Archive network because of the need to get seed.txt; and
# 3. $SEED_PATH must contain the URL path to seed.txt;
#####

# Configuration
REAL_IP_MAP_DIR="/var/tmp/fast"
MAP_PATTERN="*.db"
INTERFACE="eth0"
MAX_RETRIES=60
EXIT_FLAG=false
TCPDUMP_PID=""
MKTABLE_PATH="./obfi/mktable.py"
REVEAL_PATH="./obfi/reveal.py"
SHOWNAMES_PATH="./obfi/shownames.py"

# Function to print usage information
usage() {
  echo "Usage: $0 [options] [IP_ADDRESS]"
  echo
  echo "Options:"
  echo "  -h, --help          Show this help message and exit"
  echo
  echo "Arguments:"
  echo "  IP_ADDRESS          The IP address to search for in the table"
  echo
  echo "If IP_ADDRESS is provided, the script will start building the map and search for the IP."
  echo "If no IP_ADDRESS is provided, the script will print output to the screen and run indefinitely."
  EXIT_FLAG=true
  exit 0
}

# Clean up resources and stop tcpdump.
cleanup() {
  if [ "$EXIT_FLAG" = true ]; then
    return
  fi
  EXIT_FLAG=true

  printf "\nCleaning up before exit\n"
  if [ -n "$TCPDUMP_PID" ]; then
    kill "$TCPDUMP_PID"
    wait "$TCPDUMP_PID"
  fi

  find "$REAL_IP_MAP_DIR" -name "$MAP_PATTERN" -type f -mmin +60 -exec rm {} \;
  exit 0
}

# Handle interrupts (e.g. ctrl+c).
handle_interrupt() {
  cleanup
  exit 0
}

trap cleanup EXIT
trap handle_interrupt INT

# Start tcpdump and send packets to mktable for processing
start_tcpdump() {
  tcpdump -i "$INTERFACE" -n dst port 80 | "$MKTABLE_PATH"
}

# Start tcpdump in the background and send packets to mktable for processing
start_tcpdump_background() {
  nohup tcpdump -i "$INTERFACE" -n dst port 80 2>/dev/null | "$MKTABLE_PATH" > /dev/null 2>&1 &
  TCPDUMP_PID=$!
}

# Search for an obfuscated IP in the mktable database.
search_for_ip_in_table() {
  local input_ip="$1"
  for ((i=1; i<=MAX_RETRIES; i++)); do
    local output
    output=$(echo "$input_ip" | "$REVEAL_PATH" | "$SHOWNAMES_PATH")

    if echo "$output" | grep "("; then
      exit 0
    fi

    if (( i % 10 == 0 )); then
      echo "Attempt $i out of $MAX_RETRIES"
    fi

    sleep 1
  done

  echo "No matches were found after $MAX_RETRIES tries."
}

main() {
  if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
  fi

  if ! [ -n "$SEED_PATH" ]; then
    echo "Set \$SEED_PATH to the URL path to seed.txt"
    echo "Did you try sudo -E $0?"
    EXIT_FLAG=true
    exit 1
  fi

  if [ -z "$1" ]; then
    # Print to STDOUT and run indefinitely.
    start_tcpdump
  else
    # Spend up to $MAX_RETRIES looking for one IP.
    start_tcpdump_background
    search_for_ip_in_table "$1"
  fi
}

main "$@"
