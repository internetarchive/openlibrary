def pytest_funcarg__compare_results(request):
    """Returns a function to compare two objects d1 an d2 recursively
    skipping the 'key' if present parameter"""
    def compare_results(d1, d2):
        print compare_results.depth * 2 * "--" +  "Comparing\n","1 ==> ",d1, "\n2 ==> ", d2
        if d1 == d2: # Trivially the same
            return True
        if isinstance(d1, list) and isinstance(d2, list) and len(d1) == len(d2):
            for i,j in zip(d1, d2):
                compare_results.depth += 1
                ret = compare_results(i, j)
                compare_results.depth -= 1
                print " ==> ",ret, "\n"
                if ret:
                    pass
                else:
                    return False
            return True

        if isinstance(d1, dict) and isinstance(d2, dict) and len(d1.keys()) == len(d2.keys()):
            for k,v in d1.iteritems():
                if k != 'key':
                    compare_results.depth += 1
                    ret = compare_results(d1.get(k), d2.get(k))
                    print " ==> ",ret, "\n"
                    compare_results.depth -= 1
                    if ret:
                        pass
                    else:
                        return False
            return True
        return False
    return compare_results
