  
  var DEFAULT_EXPIRE = 7200000;
  var DEFAULT_THRESH = 2;
  var REFRESH_RATE = 10;
  var KEEP = 2000; // ?
  var LIST_LIMIT = 20;
  var WP_API_URL = 'https://en.wikipedia.org/w/api.php'
  var BOOTUP_API_URL = 'http://wikimedia-foundation-2.local:5000/recent/?callback=?';
  var change_templ;

  var RC_FEED_URL = 'ws://wikimon.hatnote.com/en/';
  var EVENTS_FEED_URL = 'ws://localhost:9000';

  $(function() {
    $('#modal-template').hide();
    $('#expire-time').html(DEFAULT_EXPIRE / 1000)
    change_templ = $('.edit-item:first');
    $('.item-action').on('click', function(e) {
      e.preventDefault();
      
    })
  })

  function format_number(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  var change = function(wid, data) {
    this.data = data;
    this.wid = wid;
    this.title = data['page_title'];
    this.user = 'User:' + data['user'];
    // parse out date
    this.date = Date.now();
    this.is_revert = function() {
      var summary = data['summary'] ? data['summary'].toLowerCase() : '';
      if (summary.indexOf('revert') > -1) {
        return true;
      }
      if (summary.indexOf('undo') > -1) {
        return true;
      }
      if (summary.indexOf('undid') > -1) {
        return true;
      }
      if (summary.indexOf('rv ') == 0) {
        return true;
      }
      return false
    }
    if ('recv_time' in data) {
      var epoch_temp = new Date(0);
      this.date = epoch_temp.setUTCSeconds(data['recv_time']);
    } 
    this.age = function() {
      return Date.now() - this.date;
    }

    this.decayed = function() {
      var decay = (DEFAULT_EXPIRE - this.age()) / DEFAULT_EXPIRE;
      if (decay <= 0) {
        return 0
      } else {
        return decay
      }
    }

    this.expired = function(expire) {
      expire = typeof expire !== 'undefined' ? expire : DEFAULT_EXPIRE;
      if (this.age() > expire) {
        return true;
      }
      return false;
    }

  }

  function modal_click(d) {
    var url = WP_API_URL;
    var params = {
      'action': 'query',
      'list': 'users',
      'ususers': d['username'].replace('User:', ''),
      'usprop': 'editcount|registration',
      'format': 'json',
      'cmlimit': 100
    }

    var cur_item = d3.select(this.parentNode);
    var modal = $('#modal-template').clone();
    var title_list = $.map(d['edits']
      .slice(d['edits'].length - 3), function(e) { 
        return '<li><a href="' + e['data']['url'] + '" target="_blank">' + e['title'] + '</a> (' + e['data']['change_size'] + ')</li>';
      }).join('\n');
    // 
    modal.find('h2')
      .text(d['username'].replace('User:', ''));
    modal.find('.username:first')
      .text(d['username'].replace('User:', ''))
      .parent()
      .attr('href', 'https://en.wikipedia.org/wiki/' + d['username']);
    modal.find('.count:first')
      .text(d['edits'].length);
    modal.find('.recent-list:first')
      .html('<ul>' + title_list + '</ul>');
    if (!d['edits'][0]['data']['is_anon']) {
      $.ajax({
        dataType: 'jsonp',
        url: url,
        data: params,
      }).done(function(resp) {
        var user_info = resp['query']['users'][0];
        if (user_info['name'] != d['username'].replace('User:', '')) {
          console.log('Error, non-matching user info: ', user_info);
          return;
        }
        modal.find('.edit-count:first')
          .text(format_number(user_info['editcount']));
        modal.find('.join-date:first')
          .text(new Date(user_info['registration']).toDateString());
      });
    } else {
      modal.find('.edit-count:first').parents('li').remove();
      modal.find('.join-date:first')
        .parents('li')
        .remove();
      modal.find('ul:first')
        .append('<li>This is an unregistered user. Remember, <a href="https://en.wikipedia.org/wiki/Wikipedia:IPs_are_people_too" target="_blank">IPs are human too</a>!</li>');
    }
    modal
      .leanModal();
  }

  function update(selector, data, limit) {
    limit = limit ? limit : LIST_LIMIT;
    data = data.slice(0, limit);
    var edit_item = d3.select(selector).selectAll('.item')
      .data(data, function(d) {
        return d['username'];
      });

    edit_item
      .order()
      .each(function(d, i) {
        var cur_item = d3.select(this);
        var num = d['edits'].length;
        cur_item.select('a.last-edit')
          .attr('href', 'https://' + d['edits'][num - 1].wid + '.wikipedia.org/wiki/' + d['edits'][num - 1].title)
          .text(d['edits'][num - 1].title);
        cur_item.select('span.count').html(num);
        cur_item.select('span.score').html(d['score']);
        cur_item.select('span.size').html(d['size']);
        cur_item.select('span.size-rel').html(d['size_rel']);
        cur_item.select('span.minor-edits').html(d['minor_edits']);
        cur_item.select('span.new-edits').html(d['new_edits']);
        cur_item.select('span.reverts').html(d['reverts']);
        cur_item.select('.item-action')
          .on('click', modal_click);
      });
    item_enter = edit_item
      .order()
      .enter()
      .append('li')
      .attr('class', 'item')
      .each(function(d, i) {
        //console.log('entering ', d)
      });
    item_enter
      .append('span')
      .attr('class', 'item-user')
      .text(function(d) {
        return  d['username'].replace('User:', '') + ' ';
      });
    item_enter
      .append('span')
      .attr('class', 'item-action')
      .text(function(d) {
        return 'Give barnstar';
      })
      .on('click', modal_click);
    item_enter
      .append('div')
      .attr('class', 'item-stats')
      .each(function(d) {
        var cur_item = d3.select(this);
        var num = d['edits'].length;
        var last_edit = d['edits'][num - 1];
        var wid = d['edits'][num - 1].wid;
        stats_list = cur_item.append('ul');
        stats_list
          .append('li')
          .html('Recently edited <a class="last-edit" href="https://' + wid + '.wikipedia.org/wiki/' + last_edit.title + '">' + last_edit.title + '</a>.');
        stats_list
          .append('li')
          .html('<span class="count">' + num + '</span> recent edits</li>');
        stats_list
          .append('li')
          .attr('class', 'score')
          .html('Score: <span class="score">' + d['score'] + '</span>');
        stats_list
          .append('li')
          .html('Size: <span class="size">' + d['size'] + '</span> (<span class="size-rel">' + d['size_rel'] + '</span>)');
        stats_list
          .append('li')
          .html('Minor edits: <span class="minor-edits">' + d['minor_edits'] + '</span>');
        stats_list
          .append('li')
          .html('New edits: <span class="new-edits">' + d['new_edits'] + '</span>');
        stats_list
          .append('li')
          .html('Reverts: <span class="reverts">' + d['reverts'] + '</span>');
      });
    edit_item.exit()
      .remove();
  }


  var recent_changes = function() {
    this.active = [];
    this.expired = [];
    this.groups = {
      'by_title': {},
      'by_user': {}
    }
    this.interesting = {
      'by_title': [],
      'by_user': []
    };
    this.total_counter = 0;

    this.add = function(wid, data) {
      edit = new change(wid, data);
      this.active.push(edit);
      this.total_counter += 1;
    }

    this.update_groups = function() {
      // reset the counters
      this.groups = {
        'by_title': {},
        'by_user': {}
      }

      for (var i = 0; i < this.active.length; i++) {
        var cur_change = this.active[i];
        // move expired changes to this.expired
        if (cur_change.expired()) {
          this.active.splice(i, 1);
          this.expired.push(cur_change)
        } else {
          // counter by title
          if (cur_change.title in this.groups['by_title']) {
            this.groups['by_title'][cur_change.title].push(cur_change);
          } else {
            this.groups['by_title'][cur_change.title] = [cur_change]
          }
          // count changes by user
          if (cur_change.user in this.groups['by_user']) {
            this.groups['by_user'][cur_change.user].push(cur_change);
          } else {
            this.groups['by_user'][cur_change.user] = [cur_change]
          }
        }
      }
      if (this.expired > KEEP) {
          // keep these around for how long?
      }
    }

    this.get_interesting = function(threshold) {
      threshold = typeof threshold !== 'undefined' ? threshold : DEFAULT_THRESH;
      this.interesting = {
        'by_title': [],
        'by_user': []
      };

      for (var user in this.groups['by_user']) {
        if (this.groups['by_user'].hasOwnProperty(user)) {
          var cur_user = this.groups['by_user'][user];
          // calculate by threshold recent edits
          if (cur_user.length >= threshold) {
            var ret = {
              'username': user,
              'score': cur_user.reduce(function (a, b) {
                  return a + b.decayed();
                }, 0),
              'edits': cur_user,
              'size': cur_user.reduce(function (a, b) {
                var size = Math.abs(b['data']['change_size'])
                if (b['data']['ns'] != 'Main' || b.is_revert()) {
                  //only count main ns and no reverts
                  size = 0;
                }
                return a + size;
              }, 0),
              'size_rel': cur_user.reduce(function (a, b) {
                var size_rel = Math.abs(b['data']['change_size']) * b.decayed();
                if (b['data']['ns'] != 'Main' || b.is_revert()) {
                  //only count main ns and no reverts
                  size_rel = 0;
                }
                return a + size_rel;
              }, 0),
              'minor_edits': cur_user.filter(function(rev) {
                return rev['data']['is_minor'] === true;
              }).length,
              'new_edits': cur_user.filter(function(rev) {
                return rev['data']['is_bot'] === true;
              }).length,
              'reverts': cur_user.filter(function(rev) {
                return rev.is_revert();
              }).length,
              'new_pages': cur_user.filter(function(rev) {
                return rev['data']['is_new'] === true;
              }).length,
              'ns_counts': cur_user.reduce(function(counter, rev) {
                var ns = rev['data']['ns'];
                counter[ns] = (counter[ns] ? counter[ns] + 1 : 1);
                return counter;
              }, {})
            }
            this.interesting['by_user'].push(ret)
          }
        }
      }
      this.interesting['by_user'].sort(function(a, b) {
        return b['score'] - a['score'];
      })
    }
    this.show_interesting = function () {
      this.get_interesting()
      return this.interesting
    }
  }

  function multi_updater(data) {
    update('#edits', data);
    var gnomes = data.filter(function(d) {
      return d['minor_edits'] > 1;
    }).sort(function(a, b) {
      return b['minor_edits'] - a['minor_edits'];
    });
    update('#minor-edits', gnomes, 3);
    var substantial = data.sort(function(a, b) {
      return b['size_rel'] - a['size_rel'];
    })
    update('#substantial', substantial, 3);
    var vandal_fighters = data.filter(function(d) {
      return d['reverts'] > 1;
    }).sort(function(a, b) {
      return b['reverts'] - a['reverts'];
    })
    update('#vandal-fighters', vandal_fighters, 3);


  }

  function eventSocket() {

  };

  eventSocket.init = function() {
    if (this.connection) {
       this.connection.close();
    }

    if ('WebSocket' in window) {
      var wiki_changes = new recent_changes;
      var connection = new ReconnectingWebSocket(EVENTS_FEED_URL);
      this.connection = connection;
      
      connection.onopen = function() {
        console.log('Event connection open');
      };

      connection.onclose = function() {
        console.log('Event connection closed ...')
      };

      connection.onerror = function(error) {
        console.log('Event connection Error: ' + error);
      };

      connection.onmessage = function(resp) {
        var data = JSON.parse(resp.data);
        console.log(data);
      };
    }
  };

  eventSocket.close = function() {
    if (this.connection) {
      this.connection.close();
    }
  };

  function enWikipediaSocket() {

  };

  enWikipediaSocket.init = function() {
    if (this.connection) {
       this.connection.close();
    }

    if ('WebSocket' in window) {
      var wiki_changes = new recent_changes;
      var connection = new ReconnectingWebSocket(RC_FEED_URL);
      this.connection = connection;
      var ns_counts = {}

      $.getJSON(BOOTUP_API_URL, function(resp) {
        for(var i = 0; i < resp.length; i++) {
          if (resp[i]['ns'] !== 'Special' && !resp[i]['is_bot']) {
            wiki_changes.add('en', resp[i]);
          }
        }
        wiki_changes.update_groups();
        interesting = wiki_changes.show_interesting();
        multi_updater(interesting['by_user']);
      });

      // var highlight_set = setInterval(function() {
      //   var highlights = $('#highlights li');
      //   var interesting = wiki_changes.show_interesting()['by_user'];
      //   if (highlights.length > 3) {
      //     highlights[highlights.length - 1].fadeOut('300', function() {
      //       $(this).remove();
      //     });
      //   }
      //   if (interesting) {
      //     var i = Math.floor(Math.random() * (interesting.length > LIST_LIMIT ? LIST_LIMIT : interesting.length))
      //     var choice = interesting[i];
      //     $('#highlights')
      //       .prepend('<li>' + choice['username'] + '</li>')
      //       .fadeIn('600');
      //   }
      // }, 15000)
      

      connection.onopen = function() {
        console.log('Connection open!');
      };

      connection.onclose = function() {
        console.log('Connection closed ...')
      };

      connection.onerror = function(error) {
        console.log('Connection Error: ' + error);
      };

      connection.onmessage = function(resp) {
        var data = JSON.parse(resp.data);
        var interesting;
        if (data['ns'] === 'Special' || data['is_bot']) {
          return;
        }

        if (ns_counts[data.ns]) {
          ns_counts[data.ns] += 1
        } else {
          ns_counts[data.ns] = 1
        }
        wiki_changes.add('en', data);
        if (wiki_changes.total_counter % REFRESH_RATE == 0) {
          wiki_changes.update_groups();
          interesting = wiki_changes.show_interesting();
          if (interesting['by_user']) {
            multi_updater(interesting['by_user']);
          }
        }
        $('#meta-active').html(wiki_changes.active.length);
        $('#meta-total').html(wiki_changes.total_counter);
        if (interesting) {
          $('#meta-score').html(interesting['by_user'].reduce(function (a, b) {
            return a + b['score'];
          }, 0));
        }
      };
    }
  };

  enWikipediaSocket.close = function() {
    if (this.connection) {
      this.connection.close();
    }
  };

  enWikipediaSocket.init();
  eventSocket.init();