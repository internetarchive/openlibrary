import { shallowRef, onBeforeUnmount } from 'vue';

const TOAST_DURATION_MS = 6000;

/**
 * Auto-dismissing toast notification for the Testing Environment panel.
 *
 * @returns {{ toast: import('vue').ShallowRef<string>, setToast: (msg: string) => void }}
 */
export function useToast() {
    const toast = shallowRef('');
    let toastTimer = null;

    function setToast(message) {
        toast.value = message;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            toast.value = '';
        }, TOAST_DURATION_MS);
    }

    onBeforeUnmount(() => clearTimeout(toastTimer));

    return { toast, setToast };
}
