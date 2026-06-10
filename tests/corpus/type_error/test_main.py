from main import process_data

def test_process_data_with_int():
    assert process_data(5) == 25  # process_data multiplies: data * data