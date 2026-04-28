#pragma once

#include <cstddef>
#include <vector>

namespace em2 {

struct NodeState {
  std::vector<double> x;
  std::vector<double> y;
  std::vector<double> z;
  std::vector<double> e;
  std::vector<double> orix;
  std::vector<double> oriy;
  std::vector<double> oriz;
  std::vector<double> eqd;
  std::vector<double> add;
  std::vector<double> you;
  std::vector<double> adh;
  std::vector<double> rep;
  std::vector<double> rec;
  std::vector<double> cod;
  std::vector<double> grd;
  std::vector<double> pld;
  std::vector<double> vod;
  std::vector<double> eqs;
  std::vector<double> hoo;
  std::vector<double> erp;
  std::vector<double> est;
  std::vector<double> mov;
  std::vector<double> dmo;
  std::vector<double> dif;
  std::vector<double> pla;
  std::vector<double> kvol;
  std::vector<int> tipus;
  std::vector<int> icel;
  std::vector<int> altre;
  std::vector<int> marge;
  std::vector<int> talone;
  std::vector<int> fix;

  [[nodiscard]] std::size_t size() const { return x.size(); }
};

}  // namespace em2
