# Open Library

![Python Build](https://github.com/internetarchive/openlibrary/actions/workflows/python_tests.yml/badge.svg)
![JS Build](https://github.com/internetarchive/openlibrary/actions/workflows/javascript_tests.yml/badge.svg)
[![Tham gia cuộc trò chuyện tại https://gitter.im/theopenlibrary/Lobby](https://badges.gitter.im/theopenlibrary/Lobby.svg)](https://gitter.im/theopenlibrary/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Mở trong Gitpod](https://img.shields.io/badge/Contribute%20with-Gitpod-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)
[![những người đóng góp](https://img.shields.io/github/contributors/internetarchive/openlibrary.svg)](https://github.com/internetarchive/openlibrary/graphs/contributors)

[Open Library](https://openlibrary.org) là một danh mục thư viện mở, có thể được chỉnh sửa, hướng tới việc tạo ra một trang web cho mỗi cuốn sách từng được xuất bản.

Bạn đang muốn bắt đầu? [Đây là hướng dẫn](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) mà bạn đang tìm. Bạn có thể muốn tìm hiểu về [Google Summer of Code (GSoC)?](https://github.com/internetarchive/openlibrary/wiki/Google-Summer-of-Code) hoặc [Hacktoberfest](https://github.com/internetarchive/openlibrary/wiki/Hacktoberfest).

## Mục lục
   - [Giới thiệu](#giới-thiệu)
   - [Cài đặt](#cài-đặt)
   - [Tổ chức code](#tổ-chức-code)
   - [Kiến trúc](#kiến-trúc)
     - [Frontend](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide)
     - [Backend](#the-backend)
     - [Kiến trúc dịch vụ](https://github.com/internetarchive/openlibrary/wiki/Production-Service-Architecture)
   - [Hướng dẫn dành cho nhà phát triển](#hướng-dẫn-dành-cho-nhà-phát-triển)
   - [Chạy tests](#chạy-tests)
   - [Đóng góp](#đóng-góp)
   - [Các API công khai](https://openlibrary.org/developers/api)
   - [Các câu hỏi thường gặp](https://openlibrary.org/help/faq)

## Giới thiệu

Open Library là một nỗ lực bắt đầu từ năm 2006 nhằm tạo ra "một trang web cho mỗi cuốn sách từng được xuất bản". Nền tảng này cung cấp quyền truy cập vào nhiều sách thuộc phạm vi công cộng và sách không còn in nữa và có thể được đọc trực tuyến.
Dưới đây là một chuyến tham quan nhanh về Open Library để giúp bạn làm quen với dịch vụ và những gì nó cung cấp (10 phút).

[![archive org_embed_openlibrary-tour-2020 (1)](https://user-images.githubusercontent.com/978325/91348906-55940d00-e799-11ea-83b9-17cd4d99642b.png)](https://archive.org/embed/openlibrary-tour-2020/openlibrary.ogv)

- [Tìm hiểu thêm về dự án Open Library](https://openlibrary.org/about)
- [Tầm nhìn (Uớc mơ) của OpenLibrary](https://openlibrary.org/about/vision)
- [Truy cập blog](https://blog.openlibrary.org)

## Cài đặt

Chạy `docker compose up` và truy cập http://localhost:8080

Cần thêm chi tiết? Xem thử [Docker instructions](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md)
hoặc [video hướng dẫn](https://archive.org/embed/openlibrary-developer-docs/openlibrary-docker-set-up.mp4).

***Ngoài ra***, nếu bạn không muốn thiết lập Open Library trên máy tính cá nhân của mình, hãy thử sử dụng Gitpod! Điều này cho phép bạn làm việc với Open Library hoàn toàn trong trình duyệt mà không cần cài đặt bất kỳ thứ gì trên máy tính cá nhân.
Cảnh báo: Sự tích hợp này vẫn đang trong giai đoạn thử nghiệm..
[![Open In Gitpod](https://img.shields.io/badge/Contribute%20with-Gitpod-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)

### Hướng dẫn dành cho nhà phát triển

Bạn cũng có thể tìm thêm thông tin về Tài liệu dành cho nhà phát triển của Open Library trong chính Open Library. [Wiki](https://github.com/internetarchive/openlibrary/wiki/).

## Tổ chức code

* openlibrary/core - chức năng cốt lõi của openlibrary, được nhập và sử dụng bởi www
* openlibrary/plugins - các mô hình, các bộ điều khiển và trình trợ giúp hiển thị khác.
* openlibrary/views - các chế độ xem để hiển thị trang web
* openlibrary/templates - tất cả những templates được dùng trên trang web.
* openlibrary/macros -  các macro tương tự như mẫu, nhưng có thể được gọi từ wikitext.

## Kiến trúc

### Backend

Open Library được phát triển dựa trên hệ thống wiki Infogami, hệ thống này lại được xây dựng trên nền tảng web.py, một framework web viết bằng Python, và framework cơ sở dữ liệu Infobase.

- [Tổng quan về các công nghệ web Backend](https://openlibrary.org/about/tech)

Sau khi bạn đã đọc tổng quan về các công nghệ Backend của Open Library, rất khuyến khích bạn đọc tài liệu hướng dẫn dành cho nhà phát triển, giải thích cách sử dụng Infogami (và cơ sở dữ liệu của nó, Infobase).

- [Tutorial dành cho nhà phát triển Infogami](https://openlibrary.org/dev/docs/infogami)

Nếu bạn muốn bắt đầu tìm hiểu thêm về mã nguồn cho Infogami, xem [Infogami repo](https://github.com/internetarchive/infogami).

## Chạy tests

Các test cho Open Library có thể được chạy bằng docker. Xin vui lòng đọc trên [Testing Document](https://github.com/internetarchive/openlibrary/wiki/Testing) để biết thêm chi tiết.

```
docker compose run --rm home make test
```

## Đóng góp

Có nhiều cách để tình nguyện viên đóng góp cho dự án Open Library, từ phát triển và thiết kế đến quản lý dữ liệu và gắn kết cộng đồng. Đây là cách bạn có thể tham gia:

### Nhà phát triển
- **Bắt đầu:** Xem thử [Contributing Guide](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) để biết thêm về các hướng dẫn về việc thiết lập môi trường development, tìm vấn đề để giải quyết, và nộp những đóng góp của bạn.
- **Những vấn đề tốt để bắt đầu (Good First Issues):** Lướt [Good First Issues](https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue+is%3Aopen+-linked%3Apr+label%3A%22Good+First+Issue%22+no%3Aassignee) để tìm những vấn đề phù hợp cho người mới bắt đầu (beginners).

### Nhà thiết kế
- **Đóng góp thiết kế:** Chúng tôi hoan nghênh những nhà thiết kế giúp đỡ cải thiện trải nghiệm người dùng. Bạn có thể bắt đầu bằng cách xem thử [design-related issues](https://github.com/internetarchive/openlibrary/labels/design).

### Thủ thư và những người đam mê dữ liệu
- **Đóng góp về dữ liệu:** Tìm hiểu cách đóng góp vào danh mục của chúng tôi và cải thiện dữ liệu sách trên Open Library!. Thăm trang [volunteer page](https://openlibrary.org/volunteer) để biết thêm thông tin.

### Gắn kết cộng đồng
- **Tham gia Community Calls:** Open Library tổ chức các cuộc gọi cộng đồng và thiết kế hàng tuần. Xem[community call schedule](https://github.com/internetarchive/openlibrary/wiki/Community-Call) để biết về giờ giấc và chi tiết.
- **Hỏi câu hỏi:** Nếu bạn có câu hỏi, tham gia [gitter chat](https://gitter.im/theopenlibrary/Lobby) hoặc yêu cầu một lời mời đến với trang Slack qua [volunteers page](https://openlibrary.org/volunteer).

Để biết thêm thông tin chi tiết, xin mời xem qua [Contributing Guide](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md).


## Giấy phép

Tất cả mã nguồn được xuất bản ở đây đều được cung cấp theo các điều khoản của giấy phép [GNU Affero General Public License, version 3](https://www.gnu.org/licenses/agpl-3.0.html).