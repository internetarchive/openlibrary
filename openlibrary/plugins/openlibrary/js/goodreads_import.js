export function initGoodreadsImport(){      
      $(document).on('click', 'th.toggle-all input', function(){
        var checked = $(this).attr('checked');
        if(!checked){
          $(this).removeAttr('checked');
          $('input.add-book').each(function() {
          $(this).removeAttr('checked');
          });
        }
        else{
          $(this).attr('checked', 'checked')
          $('input.add-book').each(function() {
            $(this).attr('checked', 'checked');
          });
        }
        var l = $(`.add-book[checked*='checked']`).size();
        $('.import-submit').attr('value', 'Import '+ l + ' Books');
      });

      $(document).on('click', 'input.add-book', function(){
        var checked = $(this).attr('checked');
        if(!checked){
          $(this).removeAttr('checked');
        }
        else{
          $(this).attr('checked', 'checked');
        }
        var l = $(`.add-book[checked*='checked']`).size();
        $('.import-submit').attr('value', 'Import '+ l + ' Books');
      });

      function func1(value){
        var l = $(`.add-book[checked*='checked']`).size();
        var elem = document.getElementById('myBar');
        elem.style.width = value*(100/l) + '%';
        elem.innerHTML = value  + ' Books';
        if(value*(100/l) >= 100){
          elem.innerHTML = '';
          $('#myBar').append(`<a href='/account/books' style='color:white'> Go to your Reading Log </a>`);
          $('.cancel-button').addClass('hidden');
        }
        console.log(l)
      }

      $('.import-submit').on('click', function() {
        $('#myProgress').removeClass('hidden');
        $('.cancel-button').removeClass('hidden');
        console.log('In Import Books')
        $('input.import-submit').addClass('hidden');
        $('th.import-status').removeClass('hidden');
        $('th.status-reason').removeClass('hidden');
        var count = 0;
        var prevPromise = Promise.resolve();
        $('input.add-book').each(function(){
              var input = $(this),
                  checked = input.attr('checked');
              console.log(typeof input.val());
              console.log(input.val());
              var value = JSON.parse(input.val().replace(/'/g,'\"'));
              console.log(value);
              console.log(value['Exclusive Shelf']);
              console.log(value['My Rating']);
              var shelf = value['Exclusive Shelf'];
              var shelf_id = 0;
              if(shelf == 'read')
                shelf_id = 3;
              else if(shelf == 'to-read')
                shelf_id = 1;
              else if(shelf == 'currently-reading')
                shelf_id = 2;
              if(checked && shelf_id!=0){
                console.log('Yes----------');
                prevPromise = prevPromise.then(function() { // prevPromise changes in each iteration
                  $('tr.table-row.'+value['ISBN']).addClass('selected');
                  return getWork(value['ISBN']); // return a new Promise
                }).then(function(data) {
                  console.log('Yes----------')
                  var obj = JSON.parse(data)
                  $.ajax({
                      url: obj['works'][0].key + '/bookshelves.json',
                      type: 'POST',
                      data: {
                          dont_remove: true,
                          edition_id: obj['key'],
                          bookshelf_id: shelf_id
                      },
                      datatype: 'json',
                      success: function() {
                          console.log('Book Added to the Reading Log');
                          if(value['My Rating']!='0'){
                            $.ajax({
                              url: obj['works'][0].key + '/ratings.json',
                              type: 'POST',
                              data: {
                                  rating: parseInt(value['My Rating']),
                                  edition_id: obj['key'],
                                  bookshelf_id: shelf_id
                              },
                              datatype: 'json',
                              success: function() {
                                  console.log('Rating Added to the Book');
                                  $('tr.table-row.'+value['ISBN']).append(`<td class='success-imported'>Imported</td>`)
                                  $('tr.table-row.'+value['ISBN']).removeClass('selected');
                              },
                              fail: function(){
                                  $('tr.table-row.'+value['ISBN']).append(`<td class='error-imported'>Error</td><td class='error-imported'>Failed to add Rating</td>`)
                                  $('tr.table-row.'+value['ISBN']).removeClass('selected');
                              }
                            });
                          }
                          else{
                            $('tr.table-row.'+value['ISBN']).removeClass('selected');
                          }
                        },
                      fail: function(){
                          $('tr.table-row.'+value['ISBN']).append(`<td class='error-imported'>Error</td><td class='error-imported'>Failed to add book to reading log</td>`)
                          $('tr.table-row.'+value['ISBN']).removeClass('selected');
                      }
                  });
                  console.log(obj['key']);
                  console.log(obj['works'][0].key);
                  func1(++count);
                }).catch(function(error) {
                  $('tr.table-row.'+value['ISBN']).append(`<td class='error-imported'>Error</td><td class='error-imported'>Book not in collection</td>`)
                  $('tr.table-row.'+value['ISBN']).removeClass('selected');
                  console.log(error);
                  func1(++count);
                });
              }
              else if(checked && shelf_id == 0){
                $('tr.table-row.'+value['ISBN']).append(`<td class='error-imported'>Error</td><td class='error-imported'>Book in different Shelf</td>`);
                func1(++count);
              }
          });
          $('td.books-wo-isbn').each(function(){
              $(this).removeClass('hidden');
          });
      });

      function getWork(isbn) {
        return new Promise(function(resolve, reject) {
          var request = new XMLHttpRequest();

          request.open('GET', '/isbn/' + isbn + '.json');
          request.onload = function() {
            if (request.status === 200) {
              resolve(request.response); // we get the data here, so resolve the Promise
            } else {
              reject(Error(request.statusText)); // if status is not 200 OK, reject.
            }
          };

          request.onerror = function() {
            reject(Error('Error fetching data.')); // error occurred, so reject the Promise
          };

          request.send(); // send the request
        });
      }

      function getWork(isbn) {
        return new Promise(function(resolve, reject) {
          var request = new XMLHttpRequest();

          request.open('GET', '/isbn/' + isbn + '.json');
          request.onload = function() {
            if (request.status == 200) {
              resolve(request.response); // we get the data here, so resolve the Promise
            } else {
              reject(Error(request.statusText)); // if status is not 200 OK, reject.
            }
          };

          request.onerror = function() {
            reject(Error('Error fetching data.')); // error occurred, so reject the Promise
          };

          request.send(); // send the request
        });
      }
}