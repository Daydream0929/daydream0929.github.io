# 深入浅出CUDA线程模型索引

## 线程模型
以一维线程模型为例，假设一共32个threads，根据不同的block大小，线程索引如下

<img src="https://raw.githubusercontent.com/Daydream0929/daydream0929.github.io/master/_screenshots/2024-02-24_1.png" width="50%" height=auto class="center"/>

## 高维坐标--->一维坐标
假设有一个三维坐标(x, y, z)，各个维度的大小分别为Dx, Dy, Dz。则一维坐标表示为
* id = z * Dx * Dy + y * Dx + x
理解了高维坐标向一维坐标的转化，结合理解CUDA线程模型，那么CUDA线程模型的索引就很容易理解了。


## 源代码及结果
```
#include "error.cuh"

__global__ void test()
{
    const int bx = blockIdx.x;
    const int by = blockIdx.y;
    const int tx = threadIdx.x;
    const int ty = threadIdx.y;
    const int tz = threadIdx.z;
    const int bid = by * blockDim.x + bx; // // 整个grid内部的block_idx
    const int block_tid = tz * (blockDim.x * blockDim.y) + ty * blockDim.x + tx;    // 每个block内部的thread_idx
    const int global_tid = bid * (blockDim.x * blockDim.y * blockDim.z) + block_tid;    // 整个grid内部的thread_idx
    printf("bid: %d  --- block_tid : %d  --- globa_tid : %d\n", bid, block_tid, global_tid);
}

int main()
{
    dim3 blocks_per_grid = {2, 2, 1};
    dim3 threads_per_block = {2, 3, 4};
    test<<<blocks_per_grid, threads_per_block>>>();
    cudaDeviceSynchronize();
    return 0;
}
```

```
bid: 0  --- block_tid : 0  --- globa_tid : 0
bid: 0  --- block_tid : 1  --- globa_tid : 1
bid: 0  --- block_tid : 2  --- globa_tid : 2
bid: 0  --- block_tid : 3  --- globa_tid : 3
bid: 0  --- block_tid : 4  --- globa_tid : 4
bid: 0  --- block_tid : 5  --- globa_tid : 5
bid: 0  --- block_tid : 6  --- globa_tid : 6
bid: 0  --- block_tid : 7  --- globa_tid : 7
bid: 0  --- block_tid : 8  --- globa_tid : 8
bid: 0  --- block_tid : 9  --- globa_tid : 9
bid: 0  --- block_tid : 10  --- globa_tid : 10
bid: 0  --- block_tid : 11  --- globa_tid : 11
bid: 0  --- block_tid : 12  --- globa_tid : 12
bid: 0  --- block_tid : 13  --- globa_tid : 13
bid: 0  --- block_tid : 14  --- globa_tid : 14
bid: 0  --- block_tid : 15  --- globa_tid : 15
bid: 0  --- block_tid : 16  --- globa_tid : 16
bid: 0  --- block_tid : 17  --- globa_tid : 17
bid: 0  --- block_tid : 18  --- globa_tid : 18
bid: 0  --- block_tid : 19  --- globa_tid : 19
bid: 0  --- block_tid : 20  --- globa_tid : 20
bid: 0  --- block_tid : 21  --- globa_tid : 21
bid: 0  --- block_tid : 22  --- globa_tid : 22
bid: 0  --- block_tid : 23  --- globa_tid : 23
bid: 3  --- block_tid : 0  --- globa_tid : 72
bid: 3  --- block_tid : 1  --- globa_tid : 73
bid: 3  --- block_tid : 2  --- globa_tid : 74
bid: 3  --- block_tid : 3  --- globa_tid : 75
bid: 3  --- block_tid : 4  --- globa_tid : 76
bid: 3  --- block_tid : 5  --- globa_tid : 77
bid: 3  --- block_tid : 6  --- globa_tid : 78
bid: 3  --- block_tid : 7  --- globa_tid : 79
bid: 3  --- block_tid : 8  --- globa_tid : 80
bid: 3  --- block_tid : 9  --- globa_tid : 81
bid: 3  --- block_tid : 10  --- globa_tid : 82
bid: 3  --- block_tid : 11  --- globa_tid : 83
bid: 3  --- block_tid : 12  --- globa_tid : 84
bid: 3  --- block_tid : 13  --- globa_tid : 85
bid: 3  --- block_tid : 14  --- globa_tid : 86
bid: 3  --- block_tid : 15  --- globa_tid : 87
bid: 3  --- block_tid : 16  --- globa_tid : 88
bid: 3  --- block_tid : 17  --- globa_tid : 89
bid: 3  --- block_tid : 18  --- globa_tid : 90
bid: 3  --- block_tid : 19  --- globa_tid : 91
bid: 3  --- block_tid : 20  --- globa_tid : 92
bid: 3  --- block_tid : 21  --- globa_tid : 93
bid: 3  --- block_tid : 22  --- globa_tid : 94
bid: 3  --- block_tid : 23  --- globa_tid : 95
bid: 1  --- block_tid : 0  --- globa_tid : 24
bid: 1  --- block_tid : 1  --- globa_tid : 25
bid: 1  --- block_tid : 2  --- globa_tid : 26
bid: 1  --- block_tid : 3  --- globa_tid : 27
bid: 1  --- block_tid : 4  --- globa_tid : 28
bid: 1  --- block_tid : 5  --- globa_tid : 29
bid: 1  --- block_tid : 6  --- globa_tid : 30
bid: 1  --- block_tid : 7  --- globa_tid : 31
bid: 1  --- block_tid : 8  --- globa_tid : 32
bid: 1  --- block_tid : 9  --- globa_tid : 33
bid: 1  --- block_tid : 10  --- globa_tid : 34
bid: 1  --- block_tid : 11  --- globa_tid : 35
bid: 1  --- block_tid : 12  --- globa_tid : 36
bid: 1  --- block_tid : 13  --- globa_tid : 37
bid: 1  --- block_tid : 14  --- globa_tid : 38
bid: 1  --- block_tid : 15  --- globa_tid : 39
bid: 1  --- block_tid : 16  --- globa_tid : 40
bid: 1  --- block_tid : 17  --- globa_tid : 41
bid: 1  --- block_tid : 18  --- globa_tid : 42
bid: 1  --- block_tid : 19  --- globa_tid : 43
bid: 1  --- block_tid : 20  --- globa_tid : 44
bid: 1  --- block_tid : 21  --- globa_tid : 45
bid: 1  --- block_tid : 22  --- globa_tid : 46
bid: 1  --- block_tid : 23  --- globa_tid : 47
bid: 2  --- block_tid : 0  --- globa_tid : 48
bid: 2  --- block_tid : 1  --- globa_tid : 49
bid: 2  --- block_tid : 2  --- globa_tid : 50
bid: 2  --- block_tid : 3  --- globa_tid : 51
bid: 2  --- block_tid : 4  --- globa_tid : 52
bid: 2  --- block_tid : 5  --- globa_tid : 53
bid: 2  --- block_tid : 6  --- globa_tid : 54
bid: 2  --- block_tid : 7  --- globa_tid : 55
bid: 2  --- block_tid : 8  --- globa_tid : 56
bid: 2  --- block_tid : 9  --- globa_tid : 57
bid: 2  --- block_tid : 10  --- globa_tid : 58
bid: 2  --- block_tid : 11  --- globa_tid : 59
bid: 2  --- block_tid : 12  --- globa_tid : 60
bid: 2  --- block_tid : 13  --- globa_tid : 61
bid: 2  --- block_tid : 14  --- globa_tid : 62
bid: 2  --- block_tid : 15  --- globa_tid : 63
bid: 2  --- block_tid : 16  --- globa_tid : 64
bid: 2  --- block_tid : 17  --- globa_tid : 65
bid: 2  --- block_tid : 18  --- globa_tid : 66
bid: 2  --- block_tid : 19  --- globa_tid : 67
bid: 2  --- block_tid : 20  --- globa_tid : 68
bid: 2  --- block_tid : 21  --- globa_tid : 69
bid: 2  --- block_tid : 22  --- globa_tid : 70
bid: 2  --- block_tid : 23  --- globa_tid : 71
```
