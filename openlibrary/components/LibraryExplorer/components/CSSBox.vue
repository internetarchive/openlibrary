<template>
  <div class="css-box" :style="cubeStyle">
    <div class="front-face" :style="frontFaceStyle">
      <slot name="front"/>
    </div>
    <div class="left-face" :style="leftFaceStyle">
      <slot name="left"/>
    </div>
    <div class="right-face" :style="rightFaceStyle">
      <slot name="right"/>
    </div>
    <div class="back-face" :style="backFaceStyle">
      <slot name="back"/>
    </div>
    <div class="top-face" :style="topFaceStyle">
      <slot name="top"/>
    </div>
    <div class="bottom-face" :style="bottomFaceStyle">
      <slot name="bottom"/>
    </div>
  </div>
</template>

<script>
export default {
  props: {
    width: Number,
    height: Number,
    thickness: Number
  },
  computed: {
    cubeStyle() {
      return {
        width: `${this.width}px`,
        height: `${this.height}px`
      };
    },
    frontFaceStyle() {
      return {
        width: `${this.width}px`,
        height: `${this.height}px`
      };
    },
    backFaceStyle() {
      return {
        width: `${this.width}px`,
        height: `${this.height}px`,
        transform: `translate3d(100%, 0, -${this.thickness}px) rotateY(-180deg)`
      };
    },
    topFaceStyle() {
      return {
        width: `${this.width}px`,
        height: `${this.thickness}px`,
        transform: 'rotateX(90deg) translateY(-100%)'
      };
    },
    bottomFaceStyle() {
      return {
        width: `${this.width}px`,
        height: `${this.thickness}px`,
        transform: `translateY(${this.height}px) rotateX(-90deg)`
      };
    },
    leftFaceStyle() {
      return {
        width: `${this.thickness}px`,
        height: `${this.height}px`,
        transform: 'rotateY(-90deg) translateX(-100%)'
      };
    },
    rightFaceStyle() {
      return {
        width: `${this.thickness}px`,
        height: `${this.height}px`,
        transform: `translateX(${this.width}px) rotateY(90deg)`
      };
    }
  }
};
</script>

<style scoped>
.css-box {
  position: relative;
  /* Performance optimization, since the size of the css-box is independent of any of its children */
  contain: layout size;
}
.css-box > * {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0 0;
  box-sizing: border-box;
  overflow: hidden;
  overflow: clip;

  /* background: rgba(255, 0, 0, 0.5); */
}

.css-box {
  transform-style: preserve-3d;
  transform-origin: center;
  transition: transform .2s;
  transform: perspective(2000px) rotateX(-5deg) rotateY(50deg);
}
</style>

