export function getExperiment(experimentName) {
    if (typeof window === 'undefined') {
        return 'control';
    }
    return window.OL_EXPERIMENTS?.[experimentName] || 'control';
}

if (typeof window !== 'undefined') {
    window.getExperiment = getExperiment;
}
