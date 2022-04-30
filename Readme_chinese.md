# 公共图书馆

![Python Build](https://github.com/internetarchive/openlibrary/actions/workflows/javascript_tests.yml/badge.svg)
![JS Build](https://github.com/internetarchive/openlibrary/actions/workflows/python_tests.yml/badge.svg)
[![Join the chat at https://gitter.im/theopenlibrary/Lobby](https://badges.gitter.im/theopenlibrary/Lobby.svg)](https://gitter.im/theopenlibrary/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)

[公共图书馆](https://openlibrary.org)是一个开放的，可以编辑的图书平台。它为每一本已经出版的图书建立了其相关的网页。

您准备好开始了吗? [这份指南](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md)或许是您所需要的。您可能也会想要了解[谷歌编程之夏(GSoC)?](https://github.com/internetarchive/openlibrary/wiki/Google-Summer-of-Code)或者是[十月黑客庆典](https://github.com/internetarchive/openlibrary/wiki/Hacktoberfest)。

## 目录
   - [概述](#概述)
   - [安装](#安装)
   - [代码组成](#代码组成)
   - [结构](#结构)
     - [前端](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide)
     - [后端](#后端)
     - [服务架构](https://github.com/internetarchive/openlibrary/wiki/Production-Service-Architecture)
   - [给开发者的指南](#给开发者的指南)
   - [运行测试](#运行测试)
   - [欢迎您的贡献](CONTRIBUTING.md)
   - [公共应用程序接口](https://openlibrary.org/developers/api)
   - [常见问题](https://openlibrary.org/help/faq)

## 概述

公共图书馆创立于2006年，致力于“给每一本已经出版的图书建立其相关的页面”。它提供了对主流领域和绝版书籍的访问权限，允许人们在线阅读。

这个视频可以让您更快地了解公共图书馆，以及它所提供的服务（大约10分钟）。

[![archive org_embed_openlibrary-tour-2020 (1)](https://user-images.githubusercontent.com/978325/91348906-55940d00-e799-11ea-83b9-17cd4d99642b.png)](https://archive.org/embed/openlibrary-tour-2020/openlibrary.ogv)

- [进一步了解公共图书馆](https://openlibrary.org/about)
- [公共图书馆所期待的愿景（梦想）](https://openlibrary.org/about/vision)
- [访问博客](https://blog.openlibrary.org)

## 安装

执行 `docker-compose up` 并且访问 http://localhost:8080

需要更多信息？请查看 [Docker指南](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md)
或者[视频教程](https://archive.org/embed/openlibrary-developer-docs/openlibrary-docker-set-up.mp4)。

***或者***，如果您不想在本地的电脑上安装公共图书馆，您可以尝试Gitpod！这可以让您在不安装任何插件的前提下，在浏览器中使用公共图书馆。警告：此集成仍在实验中。
[![Open In Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)

### 给开发者的指南

有关管理公共图书馆实例的说明，请参考开发者的[快速入门](https://github.com/internetarchive/openlibrary/wiki/Getting-Started)指南。

您还可以在公共图书馆里的公共图书馆中找到更多关于开发说明书的信息[Wiki](https://github.com/internetarchive/openlibrary/wiki/)。

## 代码组成

* openlibrary/core - 公共图书馆的核心功能，由www导入和使用
* openlibrary/plugins - 其它模型、控制器和视图帮助器
* openlibrary/views - 网页视图的呈现
* openlibrary/templates - 所有在网页里使用的模板
* openlibrary/macros - macros和模板类似，但可以被wikitext调用

## 结构

### 后端

公共图书馆是在Infogami wiki系统的基础上开发的，该系统本身建立在web.py Python web应用框架和Infobase数据库之上。

- [后端技术概要](https://openlibrary.org/about/tech)

当您阅读完后端技术概要，我们强烈建议您阅览开发者入门手册，它解释了如何使用Infogami（及其数据库，Infobase）

- [Infogami开发者教程](https://openlibrary.org/dev/docs/infogami)

如果您想更深入地了解Infogami的源代码，请参阅[Infogami repo](https://github.com/internetarchive/infogami)。

## 运行测试

公共图书馆的测试可用pytest运行。 请参阅我们的[测试文档](https://github.com/internetarchive/openlibrary/wiki/Testing)以了解更多的信息

请在docker运行时进行测试

```
cd docker/
docker-compose exec web make test
```

### 集成测试

集成测试需要使用Splinter webdriver和谷歌浏览器。关于安装要求和运行集成测试的说明，请参阅[集成测试README](tests/integration/README.md)

## 许可证

这里发布的所有源代码都是依据以下条款[GNU Affero General Public License, version 3](https://www.gnu.org/licenses/agpl-3.0.html)。