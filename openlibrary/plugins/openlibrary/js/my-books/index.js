import MyBooksDropper from './MyBooksDropper'

export function initMyBooksDroppers(droppers) {
    for (const dropper of droppers) {
        const myBooksDropper = new MyBooksDropper(dropper)
    }
}
