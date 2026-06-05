def process_data(data):
    return data * data  # expects int, might get str

if __name__ == "__main__":
    result = process_data("hello")
    print(result)