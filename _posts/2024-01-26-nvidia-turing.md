# Nvidia Turing架构

Turing架构是Nvidia继Pascal架构后于2018年新推出的架构，包括2080Ti等显卡均使用的是Turing架构。Turing架构相较于Pascal架构增加了Cuda Core的数量，引入了DLSS，GDDR6等新的技术。本文简要介绍Turing架构的新特性，性能以及和上一代架构Pascal的对比，选择Turing架构的主要原因是我刚好有一张2080Ti的显卡，并且使用其学习CUDA编程。因此选择从此架构作为落脚点，一步步深入揭开NVIDIA显卡的架构原理。

## 新特性

### New Streaming Multiprocessor（SM）

* 添加了一条可以和floating-point指令通道同时执行的Integer的独立指令通道
* 将unify shared memory，texture caching和memory load caching整合为一体，提升了L1 cache的带宽和速率

### RT Core

* SM里面加了一条专用的流水线(ASIC)来计算射线和三角形求交，可以访问BVH

### Turing Tenor Cores

* 添加INT8和INT4精度模型
* Depp Learning Super Sampling

### GDDR6 High-Performance Memory Subsystem

* 第一个支持GDDR6的架构

### Second- Generation NVIDIA NVLink

* 100GB/s 带宽

### .....

## 性能
<img src="https://raw.githubusercontent.com/Daydream0929/daydream0929.github.io/master/_screenshots/image-20240128003001206.png" width="50%" height="100%" />

## Pascal VS Turing

![image-20240128002634916](https://raw.githubusercontent.com/Daydream0929/daydream0929.github.io/master/_screenshots/image-20240128002634916.png)

![image-20240128002725203](https://raw.githubusercontent.com/Daydream0929/daydream0929.github.io/master/_screenshots/image-20240128002725203.png)

![image-20240128002737478](https://raw.githubusercontent.com/Daydream0929/daydream0929.github.io/master/_screenshots/image-20240128002737478.png)



## 参考

* [NVIDIA Turing GPU Architecture](https://images.nvidia.com/aem-dam/en-zz/Solutions/design-visualization/technologies/turing-architecture/NVIDIA-Turing-Architecture-Whitepaper.pdf)
* [图灵微架构](https://zh.wikipedia.org/wiki/图灵微架构)

* [nvidia新发布的Turing架构里的RT Core的实质是什么?](https://www.zhihu.com/question/290167656/answer/470311731)