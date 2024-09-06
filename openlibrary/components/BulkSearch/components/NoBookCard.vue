<template>
    <div class="noBookCard">
        <p> No Books Found</p>
    </div>
</template>

<script>
export default {
}
</script>

<style>
.noBookCard{
    flex-shrink: 0;
    margin-right: 6px;
    width: 80vw;
    max-width: 300px;
    height: 120px;
    border: 1px solid #000;
    border-radius: 4px;
    display: flex;
    overflow: hidden;
    font-family: Inter, "Regular";
    color: inherit;
    text-decoration: inherit;
    position: relative;
    align-items: center;
    justify-content: center;
    &:first-child {
        animation: slideUp .8s;
      }
}
</style>
