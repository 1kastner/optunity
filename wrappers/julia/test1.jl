using Base.Test

include("optunity.jl")

testit(x,y,z) = (x-1)^2 + (y-2)^2 + (z+3)^4

result = minimize(testit, num_evals=10000, solver_name="grid search", x=[-5,5], y=[-5,5], z=[-5,5])

@test_approx_eq_eps result[1]["x"]  1.0 .2
@test_approx_eq_eps result[1]["y"]  2.0 .2
@test_approx_eq_eps result[1]["z"] -3.0 .2

testit2(x,y,z) = x^2 + (y-1)^3 + (z-2)^2

result = minimize(testit2, num_evals=10000, x=[-2,2], y=[-2,2], z=[-3,3])

@test_approx_eq_eps result[1]["x"]  0.0 .2
@test_approx_eq_eps result[1]["y"] -2.0 .2
@test_approx_eq_eps result[1]["z"]  2.0 .2