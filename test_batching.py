"""
Simple test to verify the work deletion batching logic.
Run with: python test_batching.py
"""

BATCH_SIZE = 1000


def simulate_batching(num_editions):
    """Simulates how many batches would be needed to delete a work."""
    edition_keys = [f'/books/OL{i}M' for i in range(num_editions)]
    work_key = '/works/OL123W'

    total_keys = len(edition_keys) + 1
    total_batches = (total_keys + BATCH_SIZE - 1) // BATCH_SIZE

    batches = []
    batch_num = 0
    work_deleted = False

    for i in range(0, len(edition_keys), BATCH_SIZE):
        batch_num += 1
        batch_keys = edition_keys[i : i + BATCH_SIZE]

        remaining = BATCH_SIZE - len(batch_keys)
        if i + BATCH_SIZE >= len(edition_keys) and remaining >= 1:
            batch_keys.append(work_key)
            work_deleted = True

        batches.append(
            {
                'num': batch_num,
                'size': len(batch_keys),
                'has_work': work_key in batch_keys,
            }
        )

    if not work_deleted:
        batch_num += 1
        batches.append({'num': batch_num, 'size': 1, 'has_work': True})

    return {'editions': num_editions, 'total_batches': batch_num, 'batches': batches}


def main():
    test_cases = [0, 1, 500, 999, 1000, 1001, 1999, 2000, 2500, 4000]

    print("Work Delete Batching Test")
    print("=" * 50)

    all_pass = True
    for num in test_cases:
        result = simulate_batching(num)
        total_deleted = sum(b['size'] for b in result['batches'])
        expected = num + 1

        status = "PASS" if total_deleted == expected else "FAIL"
        if status == "FAIL":
            all_pass = False

        print(f"\n{num} editions:")
        print(f"  Batches: {result['total_batches']}")
        for batch in result['batches']:
            work_note = " (with work)" if batch['has_work'] else ""
            print(f"  - Batch {batch['num']}: {batch['size']} items{work_note}")
        print(f"  Total deleted: {total_deleted}/{expected} - {status}")

    print("\n" + "=" * 50)
    print("Result: ALL PASS" if all_pass else "Result: SOME FAILED")
    return 0 if all_pass else 1


if __name__ == '__main__':
    exit(main())
