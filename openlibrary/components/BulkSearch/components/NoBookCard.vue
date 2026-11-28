<template>
    <div class="noBookCard">
        <p>{{ strings.noBooksFound }}</p>
    </div>
</template>

<script>
import { _ } from '../../../plugins/openlibrary/js/i18n.js';

export default {
    data() {
        return { strings: { noBooksFound: _('No Books Found') } };
    }
};
</script>

<style>
.noBookCard {
    flex-shrink: 0;
    margin-right: 6px;
    width: 80vw;
    max-width: 300px;
    height: 120px;
    border: 1px solid #999;
    border-radius: 4px;
    display: flex;
    overflow: hidden;
    color: inherit;
    text-decoration: inherit;
    position: relative;
    align-items: center;
    justify-content: center;
}
.noBookCard:first-child {
    animation: slideUp 0.8s;
}
</style>
