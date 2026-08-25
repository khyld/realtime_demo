def calculate_avarage(numbers):
    if not numbers:
        return 0
    return sum(numbers) / len(numbers)
def calculate_median(numbers):
    if not numbers:
        return 0
    sorted_numbers = sorted(numbers)
    n = len(sorted_numbers)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_numbers[mid - 1] + sorted_numbers[mid]) / 2
    else:
        return sorted_numbers[mid]
    
    #Ask user to provide a list of numbers
numbers_input = input("Enter a list of numbers separated by commas: ")
numbers = [float(num) for num in numbers_input.split(",")]

average = calculate_avarage(numbers)
median = calculate_median(numbers)

print(f"Average: {average}")
print(f"Median: {median}")

#Function to reverse a string
def reverse_string(s):
    return s[::-1]
#Ask user to provide a string
string_input = input("Enter a string to reverse: ")
reversed_string = reverse_string(string_input)
print(f"Reversed string: {reversed_string}")


