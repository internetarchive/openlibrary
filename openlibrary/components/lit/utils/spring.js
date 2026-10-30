/**
 * Damped-spring animation for gesture-driven motion.
 *
 * Ported from Lightbox3 (github.com/lokesh/lightbox3, MIT) — `springStep` is
 * its `src/physics/spring.ts` unchanged. The motion tokens in
 * `tokens/motion.css` cover surfaces that enter and leave on a fixed curve. A
 * spring is for an object the reader can grab mid-flight: the release velocity
 * of a drag feeds straight into the next animation, and any animation can be
 * interrupted by reading its live position and starting a new one from there.
 * A CSS transition can do neither, which is why `ol-lightbox` drives its morph
 * from here rather than from the tokens.
 */

/**
 * @typedef {Object} SpringConfig
 * @prop {number} stiffness
 * @prop {number} damping
 * @prop {number} [mass=1]
 */

/**
 * @typedef {Object} SpringState
 * @prop {number} position
 * @prop {number} velocity
 */

const POSITION_THRESHOLD = 0.01;
const VELOCITY_THRESHOLD = 0.01;
const MAX_DT = 0.02;
const SUB_STEP_DT = 0.008;
/** Longest frame a spring will integrate; a backgrounded tab resumes without a jump. */
const MAX_FRAME_S = 0.064;

// Presets, tuned in Lightbox3 for a Motion.dev-style feel.
/** Opening morph: a little overshoot, settles fast. */
export const SPRING_OPEN = { stiffness: 260, damping: 26, mass: 1 };
/** Closing morph: stiffer and well damped, so it lands without bouncing on the thumbnail. */
export const SPRING_CLOSE = { stiffness: 500, damping: 38, mass: 1 };
/** Snap-back after an abandoned drag. */
export const SPRING_SNAP = { stiffness: 300, damping: 30, mass: 1 };
/** Shrinking into the viewport centre when there is no thumbnail to return to. */
export const SPRING_SHRINK = { stiffness: 200, damping: 28, mass: 1 };
/** A soft settle for a rect that changes size after load. */
export const SPRING_SETTLE = { stiffness: 170, damping: 26, mass: 1 };

/**
 * Advance one spring by `dt` seconds toward `target`. Semi-implicit Euler,
 * sub-stepped when the frame is long so a dropped frame can't blow up.
 *
 * @param {SpringConfig} config
 * @param {SpringState} state
 * @param {number} target
 * @param {number} dt - Seconds since the last step.
 * @returns {SpringState & { settled: boolean }}
 */
export function springStep(config, state, target, dt) {
    const { stiffness: k, damping: c, mass: m = 1 } = config;

    if (dt > MAX_DT) {
        let current = { ...state };
        let remaining = dt;
        while (remaining > 0) {
            const step = Math.min(remaining, SUB_STEP_DT);
            const result = springStepSingle(k, c, m, current, target, step);
            if (result.settled) return result;
            current = result;
            remaining -= step;
        }
        return { ...current, settled: false };
    }

    return springStepSingle(k, c, m, state, target, dt);
}

function springStepSingle(k, c, m, state, target, dt) {
    const displacement = state.position - target;
    const springForce = -k * displacement;
    const dampingForce = -c * state.velocity;
    const acceleration = (springForce + dampingForce) / m;

    const newVelocity = state.velocity + acceleration * dt;
    const newPosition = state.position + newVelocity * dt;

    const settled = Math.abs(newPosition - target) < POSITION_THRESHOLD && Math.abs(newVelocity) < VELOCITY_THRESHOLD;

    return {
        position: settled ? target : newPosition,
        velocity: settled ? 0 : newVelocity,
        settled
    };
}

/**
 * Run one spring per key of `to` on a single `requestAnimationFrame` loop.
 *
 * `onFrame` receives the live values every frame, starting with `from`
 * synchronously so the first paint is already in place. The loop ends when
 * every spring settles or `doneWhen` says the motion is visually finished —
 * springs creep toward zero long after they look still, and a close that
 * waits for the maths would leave an invisible overlay up for several extra
 * frames. Either way the values snap to `to` and `onDone` runs once.
 *
 * @param {Object} options
 * @param {Record<string, number>} options.from
 * @param {Record<string, number>} options.to
 * @param {SpringConfig} options.config - Spring for every key without its own entry in `configs`.
 * @param {Record<string, number>} [options.velocity] - Initial velocity per key (e.g. a drag's release velocity).
 * @param {Record<string, SpringConfig>} [options.configs] - Per-key spring overrides.
 * @param {(values: Record<string, number>) => void} options.onFrame
 * @param {() => void} [options.onDone]
 * @param {(values: Record<string, number>) => boolean} [options.doneWhen]
 * @returns {{ cancel: () => void, current: Record<string, number> }} `current` is the live
 *     values object, so a caller can read where an interrupted animation got to.
 */
export function animateSprings({ from, to, config, velocity = {}, configs = {}, onFrame, onDone, doneWhen }) {
    const keys = Object.keys(to);
    const states = {};
    const current = {};
    for (const key of keys) {
        const start = from[key] ?? to[key];
        states[key] = { position: start, velocity: velocity[key] ?? 0 };
        current[key] = start;
    }

    let rafId = 0;
    let lastTime = performance.now();

    onFrame(current);

    const finish = () => {
        rafId = 0;
        Object.assign(current, to);
        onFrame(current);
        onDone?.();
    };

    const tick = now => {
        const dt = Math.min((now - lastTime) / 1000, MAX_FRAME_S);
        lastTime = now;

        let allSettled = true;
        for (const key of keys) {
            const result = springStep(configs[key] ?? config, states[key], to[key], dt);
            states[key] = result;
            current[key] = result.position;
            if (!result.settled) allSettled = false;
        }

        onFrame(current);

        if (allSettled || doneWhen?.(current)) {
            finish();
            return;
        }
        rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);

    return {
        cancel() {
            if (rafId) cancelAnimationFrame(rafId);
            rafId = 0;
        },
        current
    };
}
