<template>
	<div>
		<label>Sample Data:
			<select v-model="selectedValue">
				<option>Choose sample...</option>
				<option value="sample1">TED’s 2018 winter reading list</option>
				<option value="sample2">2023 Public Domain Day</option>
				<option value="sample3">Holocaust Wikipedia citations</option>
			</select>
		</label>
	</div>
</template>

<script>
import {sampleData} from '../utils/samples.js';
export default {
    emits: ['sample'],
    data() {
        return {
            selectedValue: '',
        }
    },
    watch: {
        selectedValue(newValue) {
            this.$emit('sample', sampleData[newValue])
        }
    },
}
</script>
