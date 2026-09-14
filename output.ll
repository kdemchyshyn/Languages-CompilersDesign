; ModuleID = "practice1"
target triple = "x86_64-unknown-linux-gnu"
target datalayout = ""

define i32 @"main"()
{
entry:
  %"x" = alloca i32
  store i32 0, i32* %"x"
  %"y" = alloca i32
  store i32 10, i32* %"y"
  %".4" = add i32 2, 5
  %"z" = alloca i32
  store i32 %".4", i32* %"z"
  %".6" = load i32, i32* %"x"
  %".7" = add i32 %".6", 10
  %"t" = alloca i32
  store i32 %".7", i32* %"t"
  %".9" = load i32, i32* %"t"
  %".10" = load i32, i32* %"z"
  %".11" = mul i32 %".9", %".10"
  store i32 %".11", i32* %"t"
  %".13" = load i32, i32* %"t"
  %".14" = bitcast [29 x i8]* @"fmt" to i8*
  %".15" = call i32 (i8*, ...) @"printf"(i8* %".14", i32 %".13")
  ret i32 0
}

declare i32 @"printf"(i8* %".1", ...)

@"fmt" = private constant [29 x i8] c"Program exit with result %d\0a\00"