<template>
  <div class="noBookCard">
    <p> No Books Found</p>
  </div>
</template>

<script>
export default {
}
</script>

<style lang="less">
.noBookCard{
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
    &:first-child {
        animation: slideUp .8s;
      }
}
</style>
