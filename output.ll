; ModuleID = "practice1"
target triple = "x86_64-unknown-linux-gnu"
target datalayout = ""

define i32 @"main"()
{
entry:
  %"x" = alloca i32
  %"y" = alloca i32
  store i32 5, i32* %"x"
  %".3" = load i32, i32* %"x"
  %".4" = add i32 %".3", 3
  store i32 %".4", i32* %"y"
  %".6" = bitcast [29 x i8]* @"fmt" to i8*
  %".7" = load i32, i32* %"y"
  %".8" = call i32 (i8*, ...) @"printf"(i8* %".6", i32 %".7")
  ret i32 0
}

declare i32 @"printf"(i8* %".1", ...)

@"fmt" = private constant [29 x i8] c"Program exit with result %d\0a\00"