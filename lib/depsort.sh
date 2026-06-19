# lib/depsort.sh — Kahn topological sort over module `requires`. Source-only.
depsort() {
  local -A seen=() indeg=() ; local -a queue=("$@") order=() all=()
  # 1. Build the full node set (BFS over requires).
  while ((${#queue[@]})); do
    local n="${queue[0]}"; queue=("${queue[@]:1}")
    [[ -n "${seen[$n]:-}" ]] && continue
    seen[$n]=1; all+=("$n")
    local dep; while IFS= read -r dep; do
      [[ -z "$dep" ]] && continue; queue+=("$dep")
    done < <(module_requires "$n")
  done
  # 2. Edges dep -> node; compute in-degrees.
  local -A radj=()  # radj[node]="space separated deps"
  local n
  for n in "${all[@]}"; do indeg[$n]=0; done
  for n in "${all[@]}"; do
    local dep
    while IFS= read -r dep; do
      [[ -z "$dep" ]] && continue
      radj[$n]+=" $dep"; indeg[$n]=$(( ${indeg[$n]} + 1 ))
    done < <(module_requires "$n")
  done
  # 3. Kahn: start with zero in-degree, but we need deps first, so process
  #    nodes whose deps are all emitted. Use reverse: emit when indeg==0.
  local -a ready=()
  for n in "${all[@]}"; do [[ "${indeg[$n]}" -eq 0 ]] && ready+=("$n"); done
  local emitted=0
  while ((${#ready[@]})); do
    local m="${ready[0]}"; ready=("${ready[@]:1}")
    order+=("$m"); emitted=$((emitted+1))
    # For every node that requires m, decrement in-degree.
    local k
    for k in "${all[@]}"; do
      [[ " ${radj[$k]:-} " == *" $m "* ]] || continue
      indeg[$k]=$(( ${indeg[$k]} - 1 ))
      [[ "${indeg[$k]}" -eq 0 ]] && ready+=("$k")
    done
  done
  [[ "$emitted" -ne "${#all[@]}" ]] && die "dependency cycle detected among modules"
  printf '%s\n' "${order[@]}"
}
