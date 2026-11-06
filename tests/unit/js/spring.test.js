import { SPRING_CLOSE, SPRING_OPEN, animateSprings, springStep } from '../../../openlibrary/components/lit/utils/spring.js';

/** Step a spring at 60fps until it settles, returning every position. */
function settle(config, from, target, { velocity = 0, maxSteps = 1000 } = {}) {
    let state = { position: from, velocity };
    const positions = [];
    for (let i = 0; i < maxSteps; i++) {
        state = springStep(config, state, target, 1 / 60);
        positions.push(state.position);
        if (state.settled) break;
    }
    return { positions, state };
}

describe('springStep', () => {
    test('moves toward the target and settles exactly on it', () => {
        const { positions, state } = settle(SPRING_OPEN, 0, 1);
        expect(state.settled).toBe(true);
        expect(state.position).toBe(1);
        expect(state.velocity).toBe(0);
        expect(positions[0]).toBeGreaterThan(0);
        expect(positions[0]).toBeLessThan(1);
    });

    test('the open preset overshoots a little; the close preset does not', () => {
        const open = settle(SPRING_OPEN, 0, 1).positions;
        const close = settle(SPRING_CLOSE, 0, 1).positions;
        expect(Math.max(...open)).toBeGreaterThan(1);
        expect(Math.max(...close)).toBeLessThanOrEqual(1 + 0.01);
    });

    test('a release velocity is carried into the first frames', () => {
        // Flung toward the target it gets there sooner than from rest, which
        // is what makes a dismissed image feel thrown rather than released.
        const flung = settle(SPRING_CLOSE, 0, -100, { velocity: -2000 }).positions;
        const rest = settle(SPRING_CLOSE, 0, -100).positions;
        expect(flung[0]).toBeLessThan(rest[0]);
    });

    test('a long frame is sub-stepped rather than integrated in one jump', () => {
        // A single 64ms Euler step at this stiffness would overshoot wildly;
        // sub-stepping keeps it inside the same envelope as four 16ms steps.
        const whole = springStep(SPRING_OPEN, { position: 0, velocity: 0 }, 1, 0.064);
        let stepped = { position: 0, velocity: 0 };
        for (let i = 0; i < 4; i++) stepped = springStep(SPRING_OPEN, stepped, 1, 0.016);
        expect(Math.abs(whole.position - stepped.position)).toBeLessThan(0.05);
    });

    test('an already-settled state stays put', () => {
        const state = springStep(SPRING_OPEN, { position: 1, velocity: 0 }, 1, 1 / 60);
        expect(state).toEqual({ position: 1, velocity: 0, settled: true });
    });
});

describe('animateSprings', () => {
    test('paints the start synchronously and the end exactly once settled', async () => {
        const frames = [];
        const done = vi.fn();
        animateSprings({
            from: { x: 0, opacity: 0 },
            to: { x: 100, opacity: 1 },
            config: SPRING_CLOSE,
            onFrame: v => frames.push({ ...v }),
            onDone: done
        });
        expect(frames[0]).toEqual({ x: 0, opacity: 0 });

        await vi.waitFor(() => expect(done).toHaveBeenCalledTimes(1), { timeout: 5000 });
        expect(frames.at(-1)).toEqual({ x: 100, opacity: 1 });
    });

    test('doneWhen ends the loop early and still snaps to the target', async () => {
        const done = vi.fn();
        const anim = animateSprings({
            from: { opacity: 1 },
            to: { opacity: 0 },
            config: SPRING_CLOSE,
            onFrame: () => {},
            onDone: done,
            doneWhen: v => v.opacity < 0.5
        });
        await vi.waitFor(() => expect(done).toHaveBeenCalledTimes(1), { timeout: 5000 });
        expect(anim.current.opacity).toBe(0);
    });

    test('cancel stops the loop without calling onDone', async () => {
        const done = vi.fn();
        const anim = animateSprings({
            from: { x: 0 },
            to: { x: 100 },
            config: SPRING_OPEN,
            onFrame: () => {},
            onDone: done
        });
        anim.cancel();
        await new Promise(resolve => setTimeout(resolve, 100));
        expect(done).not.toHaveBeenCalled();
        expect(anim.current.x).toBe(0);
    });
});
