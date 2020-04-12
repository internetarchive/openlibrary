#!/bin/bash

JOB=$1
START_AT=$2
LIMIT=$3
EXTRA_OPTS="$4"

START_SUFFIX=${START_AT//\//}
DATE_SUFFIX=`date +%Y-%m-%d_%H-%M-%S`
RUN_SIG=solr_builder_${JOB}_${START_SUFFIX}_${LIMIT}_${DATE_SUFFIX}

BOUNDS=""
if [[ $JOB == "orphans" ]]; then
    BOUNDS=""
    RUN_SIG="solr_builder_${JOB}_${DATE_SUFFIX}"
else
    BOUNDS="--start-at $START_AT --limit $LIMIT"
fi

LOG_FILE="logs/${RUN_SIG}.log"
PROGRESS_FILE="progress/${RUN_SIG}.progress"
PROFILE_FILE="profile/${RUN_SIG}.profile"

# Use "python -m cprofilev -a 0.0.0.0" to get live profiling at port 3000
python solr_builder.py $JOB $BOUNDS --progress-file "$PROGRESS_FILE" $EXTRA_OPTS &> "$LOG_FILE"
