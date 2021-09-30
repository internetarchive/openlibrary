<template>
  <div>
    <span class="pending-indicator" v-show="'PENDING' === submissionStatus.status"></span>
    <span class="success-indicator" v-show="'SUCCESS' === submissionStatus.status">Review saved!</span>
    <span class="failure-indicator" v-show="'FAILURE' === submissionStatus.status">Submission failed</span>
  </div>
</template>

<script>
export default {
    name: 'SubmissionIndicator',
    props: {
        /**
         * Object representing the state of the most recent observation POST.
         *
         * There are four states:
         *   'INACTIVE': The initial state. No POSTs have been made yet.
         *   'PENDING': Awaiting POST response from server.
         *   'SUCCESS': POST message was successfully processed.
         *   'FAILURE': POSTed observation was not persisted.
         *
         * @example
         * {
         *   "status": "PENDING"
         * }
         */
        submissionStatus: {
            type: Object,
            required: true,
            validator: function (obj) {
                return ['INACTIVE','PENDING','SUCCESS','FAILURE'].indexOf(obj.status) !== -1
            }
        }
    }
}
</script>

<style scoped>
.failure-indicator {
  color: red;
}

.success-indicator {
  color: green;
}

.pending-indicator{
  display: inline-block;
  width: 1em;
  height: 1em;
}

.pending-indicator:after {
  content: " ";
  display: block;
  width: 1em;
  height: 1em;
  border-radius: 50%;
  border: 1px solid black;
  border-color: black transparent;
  animation: pending-indicator 1.2s linear infinite;
}

@keyframes pending-indicator {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>
