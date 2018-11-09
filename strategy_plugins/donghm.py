a = [1, 2, 3, 4, 5, 6, 7]
serial_ratio = 0.3
batch = int(serial_ratio * len(a))

temp = a

while len(temp):
    print(temp[:batch])
    temp = temp[batch:]
