import { getListSaveAction } from '../../../openlibrary/components/BulkSearch/utils/listSave.js'

describe('Bulk search list save action', () => {
    test('requires a selected list target', () => {
        expect(getListSaveAction('', 'OL1W', 1, '/account/lists/add?seeds=OL1W')).toEqual({
            error: 'Please select a list.'
        })
    })

    test('requires matched books', () => {
        expect(getListSaveAction('/people/openlibrary/lists/OL1L/add', '', 0, '/account/lists/add?seeds=')).toEqual({
            error: 'No matched books to add.'
        })
    })

    test('opens the new-list URL for small matched sets', () => {
        expect(getListSaveAction('create', 'OL1W', 1, '/account/lists/add?seeds=OL1W')).toEqual({
            method: 'GET',
            url: '/account/lists/add?seeds=OL1W'
        })
    })

    test('posts to create a new list for large matched sets', () => {
        expect(getListSaveAction('create', 'OL1W,OL2W', 50, '/account/lists/add?seeds=OL1W,OL2W')).toEqual({
            method: 'POST',
            action: '/account/lists/add',
            seeds: 'OL1W,OL2W'
        })
    })

    test('opens an existing list add URL for small matched sets', () => {
        expect(getListSaveAction('/people/openlibrary/lists/OL1L/add', 'OL1W,OL2W', 2, '')).toEqual({
            method: 'GET',
            url: '/people/openlibrary/lists/OL1L/add?seeds=OL1W%2COL2W'
        })
    })

    test('posts to an existing list add URL for large matched sets', () => {
        expect(getListSaveAction('/people/openlibrary/lists/OL1L/add', 'OL1W,OL2W', 50, '')).toEqual({
            method: 'POST',
            action: '/people/openlibrary/lists/OL1L/add',
            seeds: 'OL1W,OL2W'
        })
    })
})
