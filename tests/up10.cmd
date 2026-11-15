h2 python3 tests/concurrent_tests.py 10.0.0.1 3 upload tests/files/5MB.bin E2_up_N10 > results/h2.out 2>&1 &
h3 python3 tests/concurrent_tests.py 10.0.0.1 3 upload tests/files/5MB.bin E2_up_N10 > results/h3.out 2>&1 &
h5 python3 tests/concurrent_tests.py 10.0.0.1 2 upload tests/files/5MB.bin E2_up_N10 > results/h5.out 2>&1 &
h6 python3 tests/concurrent_tests.py 10.0.0.1 2 upload tests/files/5MB.bin E2_up_N10 > results/h6.out 2>&1 &
